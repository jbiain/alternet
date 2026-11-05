"""Allowlist network egress for sandboxed apps that need a little network (e.g. an AI agent that must reach
its model API) without handing them the host's network.

The sandbox gets NO network namespace access. Inside it, `bridge()` listens on 127.0.0.1 and forwards TCP to
a unix socket in the session's scratch directory; outside, `AllowProxy` answers HTTP CONNECT on that socket,
and only tunnels to allowlisted hostnames on port 443 whose resolved addresses are public (so a hostile app
cannot reach the host's localhost services or the local network, even via DNS tricks)."""
import ipaddress, os, select, socket, sys, threading


def host_allowed(host, allow):
    host = host.lower().rstrip(".")
    for rule in allow:
        rule = rule.lower()
        if rule.startswith("."):
            if host.endswith(rule):
                return True
        elif host == rule:
            return True
    return False


def _public(addr):
    ip = ipaddress.ip_address(addr)
    return ip.is_global and not ip.is_multicast


def _pipe(a, b):
    socks = [a, b]
    try:
        while True:
            r, _, _ = select.select(socks, [], [], 120)
            if not r:
                return
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        return
    finally:
        for s in socks:
            try:
                s.close()
            except OSError:
                pass


class AllowProxy:
    def __init__(self, sock_path, allow, log=lambda *a: None):
        self.allow, self.log = list(allow), log
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(sock_path)
        os.chmod(sock_path, 0o600)
        self.srv.listen(16)
        self.running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self.running = False
        try:
            self.srv.close()
        except OSError:
            pass

    def _accept(self):
        while self.running:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        try:
            c.settimeout(15)
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 8192:
                chunk = c.recv(4096)
                if not chunk:
                    return c.close()
                head += chunk
            parts = head.split(b"\r\n", 1)[0].decode("latin-1").split()
            if len(parts) < 2 or parts[0].upper() != "CONNECT":
                c.sendall(b"HTTP/1.1 405 Only HTTPS tunnels are allowed\r\n\r\n")
                return c.close()
            host, _, port = parts[1].rpartition(":")
            if port != "443" or not host_allowed(host, self.allow):
                self.log("proxy denied %s" % parts[1])
                c.sendall(b"HTTP/1.1 403 Not on this app's allowlist\r\n\r\n")
                return c.close()
            addrs = [a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
            if not addrs or not all(_public(a) for a in addrs):
                self.log("proxy denied %s (non-public address)" % host)
                c.sendall(b"HTTP/1.1 403 Address not allowed\r\n\r\n")
                return c.close()
            up = socket.create_connection((addrs[0], 443), timeout=15)
            c.settimeout(None)
            up.settimeout(None)
            c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            _pipe(c, up)
        except Exception:
            try:
                c.close()
            except OSError:
                pass


def bridge(sock_path, port=3128):
    """Runs INSIDE the sandbox: 127.0.0.1:port -> unix socket sock_path. Blocks forever."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(32)
    while True:
        c, _ = srv.accept()
        try:
            u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            u.connect(sock_path)
        except OSError:
            c.close()
            continue
        threading.Thread(target=_pipe, args=(c, u), daemon=True).start()


if __name__ == "__main__":
    bridge(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3128)
