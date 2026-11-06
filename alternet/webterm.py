"""A terminal in the browser: the gateway runs the ordinary `alternet open` client for each web tab and relays its
terminal over a WebSocket to xterm.js. Each tab gets its own throwaway identity (a temporary home), so a web visitor is
never mistaken for the gateway, and nothing about them is kept. Standard library only; xterm.js is vendored (MIT)."""
import base64, fcntl, hashlib, json, os, pty, re, select, shutil, signal, struct, subprocess, sys, tempfile, termios, threading, time

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
TARGET = re.compile(r"^[0-9a-f]{32}(@[0-9a-f]{32})?(/[A-Za-z0-9_.-]{1,48})?\Z")
MAX_SESSIONS, MAX_SECONDS, IDLE_SECONDS, MAX_FRAME = 4, 3600, 900, 1 << 16
GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
slots = threading.BoundedSemaphore(MAX_SESSIONS)
ASSETS = {"/terminal/xterm.js": ("xterm.js", "application/javascript"), "/terminal/xterm.css": ("xterm.css", "text/css"),
          "/terminal/term.js": ("term.js", "application/javascript"), "/terminal/LICENSE-xterm.txt": ("LICENSE-xterm.txt", "text/plain")}

PAGE = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Alternet terminal</title><link rel='stylesheet' href='/terminal/xterm.css'>
<style>body{margin:0;background:#111;color:#ddd;font:15px/1.4 Menlo,Consolas,monospace}
#form{max-width:44em;margin:3em auto;padding:0 1em}input{width:100%;box-sizing:border-box;padding:.5em;background:#000;color:#ddd;border:1px solid #555;font:inherit}
button{margin-top:.6em;padding:.4em 1em;font:inherit}#screen{display:none;padding:8px}a{color:#7cf}#bar{padding:4px 8px;color:#999}
</style></head><body>
<div id='form'><h2>Alternet terminal</h2>
<p>Open an Alternet app in this tab. Paste an address (for example <code>ADDRESS/room</code>), then Connect.</p>
<input id='target' placeholder='ADDRESS, ADDRESS/APP or SITE@ADDRESS' autocomplete='off'><button id='go'>Connect</button>
<p style='color:#999'>This page runs the client on the gateway, so the gateway operator can see what you type. For anything
private, run <code>alternet gateway</code> on your own computer and open this page there. <a href='/'>Back to the BBS</a></p></div>
<div id='bar'><span id='status'></span> <button id='quit'>Disconnect</button></div>
<div id='screen'><div id='term'></div></div>
<script src='/terminal/xterm.js'></script><script src='/terminal/term.js'></script></body></html>"""
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; "
       "img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def handle_get(h, path, query):
    """Serve /terminal pages and assets. Returns True if the request was handled."""
    if path == "/terminal":
        data = PAGE.encode()
        h.send_response(200)
        h.send_header("Content-Type", "text/html; charset=utf-8")
        h.send_header("Content-Security-Policy", CSP)
        h.send_header("Content-Length", str(len(data)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        if not getattr(h, "_head_only", False):
            h.wfile.write(data)
        return True
    if path in ASSETS:
        name, ctype = ASSETS[path]
        with open(os.path.join(WEB, name), "rb") as f:
            data = f.read()
        h.send_response(200)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(data)))
        h.send_header("Cache-Control", "public, max-age=86400")
        h.end_headers()
        if not getattr(h, "_head_only", False):
            h.wfile.write(data)
        return True
    if path == "/terminal/ws":
        _websocket(h, query)
        return True
    return False


def _frame(payload, opcode=2):
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([n]) if n < 126 else b"\x7e" + struct.pack(">H", n) if n < 65536
                                      else b"\x7f" + struct.pack(">Q", n))
    return head + payload


def _parse(buf):
    """One client frame from buf: (opcode, payload, rest), or None if incomplete. Raises ValueError on bad frames."""
    if len(buf) < 2:
        return None
    op, n, i = buf[0] & 0x0f, buf[1] & 0x7f, 2
    if not buf[1] & 0x80:
        raise ValueError("client frames must be masked")
    if n == 126:
        if len(buf) < 4:
            return None
        n, i = struct.unpack(">H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, i = struct.unpack(">Q", buf[2:10])[0], 10
    if n > MAX_FRAME:
        raise ValueError("frame too large")
    if len(buf) < i + 4 + n:
        return None
    mask, data = buf[i:i + 4], bytearray(buf[i + 4:i + 4 + n])
    for k in range(n):
        data[k] ^= mask[k & 3]
    return op, bytes(data), buf[i + 4 + n:]


def _refuse(h, code, msg):
    h.send_response(code)
    h.send_header("Content-Type", "text/plain; charset=utf-8")
    h.send_header("Content-Length", str(len(msg)))
    h.end_headers()
    h.wfile.write(msg.encode())


def _websocket(h, query):
    import urllib.parse
    q = urllib.parse.parse_qs(query)
    target = (q.get("open") or [""])[0]
    key = h.headers.get("Sec-WebSocket-Key")
    origin = h.headers.get("Origin", "")
    host = h.headers.get("Host", "")
    if (h.headers.get("Upgrade", "").lower() != "websocket" or not key
            or urllib.parse.urlparse(origin).netloc != host):         # same-origin only: no cross-site hijacking
        return _refuse(h, 403, "forbidden")
    if not TARGET.match(target):
        return _refuse(h, 400, "give an address: 32 hex characters, optionally /APP")
    if not slots.acquire(blocking=False):
        return _refuse(h, 503, "the gateway is busy (all %d terminal sessions are in use)" % MAX_SESSIONS)
    tmp = None
    pid = fd = None
    try:
        cols = max(40, min(int((q.get("cols") or ["100"])[0]), 220))
        rows = max(10, min(int((q.get("rows") or ["30"])[0]), 70))
        tmp = tempfile.mkdtemp(prefix="webterm-")
        from .home import Home
        hint = getattr(h.server, "relay_hint", None)
        Home(tmp).init(auto=False, standalone=True, connect=[hint] if hint else [])
        accept = base64.b64encode(hashlib.sha1(key.encode() + GUID).digest()).decode()
        h.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        h.wfile.flush()
        h.connection.settimeout(None)
        pid, fd = pty.fork()
        if pid == 0:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TERM": "xterm-256color", "LANG": "C.UTF-8"}
            os.execve(sys.executable, [sys.executable, "-m", "alternet", "--home", tmp, "open", target], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        _pump(h.connection, fd)
    except (OSError, ValueError):
        pass
    finally:
        if pid:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                    time.sleep(0.3)
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        break
                except (OSError, ChildProcessError):
                    break
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        slots.release()
        h.close_connection = True


def _pump(sock, fd):
    buf, start, last_in = b"", time.time(), time.time()
    while time.time() - start < MAX_SECONDS and time.time() - last_in < IDLE_SECONDS:
        r, _, _ = select.select([sock, fd], [], [], 1.0)
        if fd in r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                return
            if not data:
                return
            sock.sendall(_frame(data))
        if sock in r:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
            while True:
                got = _parse(buf)
                if got is None:
                    break
                op, payload, buf = got
                if op == 8:
                    return
                if op == 9:
                    sock.sendall(_frame(payload, 10))
                elif op in (1, 2) and payload:
                    last_in = time.time()
                    os.write(fd, payload)
