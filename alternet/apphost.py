"""Run terminal apps behind an Alternet address, safely.

`alternet app-serve` announces one address. A client runs `alternet open ADDRESS[/APP]`, and sees the app's
screen over an encrypted Reticulum link while its keystrokes go back. Every connection gets its own process
(a private copy) in a throwaway scratch directory; the host decides, per app, who may connect and what the
app can touch. See docs/013-security.md for the model.

Defaults, in order of importance:
  * the client never chooses what runs: only commands from the host's config are started;
  * apps run inside a bubblewrap sandbox (read-only system, private /tmp, scratch dir only, no network
    unless the app is configured with net=true); the host refuses to start without one unless --no-sandbox;
  * apps are `public` or `trusted` (only identities in `alternet trust`);
  * app output passes through OutputFilter on the client, which removes terminal escape sequences that can
    read your screen, clipboard or keyboard state."""
import json, os, queue, resource, shutil, signal, subprocess, sys, tempfile, threading, time
from . import net

APP, ASPECT = "alternet", "app"
HEADER = b"ALTAPP"          # client's first line: "ALTAPP <rows> <cols> <TERM> [app-name]\n"
ESCAPE = b"\x1d"            # Ctrl-] disconnects the client
MAX_SESSION_SECONDS = 1800


# ---------------------------------------------------------------- client-side output filter
class OutputFilter:
    """Streaming filter for untrusted terminal output. Keeps text, colours, cursor movement, clearing and
    scrolling; drops everything that can query the terminal (replies land in your stdin), write to the
    clipboard, set titles, resize windows or reach other protocols (OSC, DCS, APC, PM, SOS, CSI n/c/t...)."""
    MAX_SEQ = 4096
    SAFE_FINALS = set(b"mHfABCDEFGJKLMPSTXd@`rsulhq")
    SAFE_PRIVATE = {b"1", b"7", b"12", b"25", b"47", b"1000", b"1002", b"1003", b"1006", b"1015", b"1047",
                    b"1048", b"1049", b"2004", b"2026"}

    def __init__(self):
        self.pend = b""

    def _csi_ok(self, params, final):
        if final not in self.SAFE_FINALS:
            return False
        if final in b"hl":
            if not params.startswith(b"?"):
                return params in (b"4",)
            return all(p in self.SAFE_PRIVATE for p in params[1:].split(b";"))
        if final == ord("q"):
            return params.endswith(b" ") and params[:-1].isdigit() or params == b" "
        if final in b"su":
            return params == b""
        if final == ord("r"):
            return all(c in b"0123456789;" for c in params)
        return all(c in b"0123456789;:" for c in params)

    def feed(self, data):
        data = self.pend + data
        self.pend = b""
        out, i, n = bytearray(), 0, len(data)
        while i < n:
            c = data[i]
            if c != 0x1B:
                out.append(c)
                i += 1
                continue
            if i + 1 >= n:
                self.pend = data[i:]
                break
            d = data[i + 1]
            if d == 0x5B:                                        # CSI
                j = i + 2
                while j < n and 0x30 <= data[j] <= 0x3F:
                    j += 1
                while j < n and 0x20 <= data[j] <= 0x2F:
                    j += 1
                if j >= n:
                    if n - i <= self.MAX_SEQ:
                        self.pend = data[i:]
                    break
                if self._csi_ok(data[i + 2:j], data[j]):
                    out += data[i:j + 1]
                i = j + 1
            elif d in b"]P_^X":                                  # OSC / DCS / APC / PM / SOS: drop whole string
                j, end = i + 2, None
                while j < n:
                    if data[j] == 7:
                        end = j + 1
                        break
                    if data[j] == 0x1B and j + 1 < n and data[j + 1] == 0x5C:
                        end = j + 2
                        break
                    if data[j] == 0x1B and j + 1 >= n:
                        break
                    j += 1
                if end is None:
                    if n - i <= self.MAX_SEQ:
                        self.pend = data[i:]
                    break
                i = end
            elif d in b"()*+-./":                               # charset designation: ESC ( B
                if i + 2 >= n:
                    self.pend = data[i:]
                    break
                if data[i + 2] in b"B0AUK":
                    out += data[i:i + 3]
                i += 3
            elif d in b"78=>MDE":
                out += data[i:i + 2]
                i += 2
            elif 0x20 <= d <= 0x2F:                              # other intermediates (ESC # 8 ...): drop
                j = i + 2
                while j < n and 0x20 <= data[j] <= 0x2F:
                    j += 1
                if j >= n:
                    self.pend = data[i:]
                    break
                i = j + 1
            else:
                i += 2
        return bytes(out)


# ---------------------------------------------------------------- host-side config and sandbox
class App:
    def __init__(self, name, cmd, cwd=None, access="public", net=False, ro=(), env=None, seconds=MAX_SESSION_SECONDS,
                 env_file=None, allow=(), site=None, runtimes=("python3",), grant_net=False):
        if access not in ("public", "trusted"):
            raise ValueError("app %r: access must be 'public' or 'trusted'" % name)
        if not cmd and not site:
            raise ValueError("app %r has no command or site" % name)
        self.name, self.cmd, self.cwd, self.access = name, list(cmd or []), cwd, access
        self.net, self.ro, self.env, self.seconds = bool(net), list(ro), dict(env or {}), int(seconds)
        self.secrets = None                # for site apps: the only env_file names the app declared it needs
        self.site, self.runtimes, self.grant_net = site, tuple(runtimes), bool(grant_net)   # site: serve the app stored under this site id
        self.allow = list(allow)           # hostnames ("api.openai.com", ".openai.com") reachable on 443 via the proxy
        self.env_file = env_file          # KEY=VALUE lines read on the host at session start (keep it 0600)


def load_apps(home):
    """apps.json: {"apps": {"chat": {"cmd": ["python3","app4.py"], "cwd": "/opt/..", "access": "public",
    "net": false, "ro": ["/opt/venv"], "env": {}, "seconds": 1800}}}"""
    path = os.path.join(home.path, "apps.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = json.load(f).get("apps", {})
    return {n: App(n, d.get("cmd"), d.get("cwd"), d.get("access", "public"), d.get("net", False),
                   d.get("ro", ()), d.get("env"), d.get("seconds", MAX_SESSION_SECONDS), d.get("env_file"), d.get("allow", ()),
                   d.get("site"), d.get("runtimes", ("python3",)), d.get("grant_net", False)) for n, d in raw.items()}


def resolve_site_app(home, app):
    """Turn a policy entry that names a site into a runnable App: read the stored site's app.json (signature
    already verified by the Store), materialise its files read-only, and intersect what the app asks for with
    what this host's policy grants. Raises ValueError with a reason a visitor can be shown."""
    from . import appspec
    store = home.store()
    sid = store.resolve(app.site)
    body = store.info(sid) if sid else None
    if not body:
        raise ValueError("this host does not hold site %s" % app.site)
    if "app.json" not in body["files"]:
        raise ValueError("site %s is not an app (no app.json)" % app.site[:12])
    if store.missing(body):
        raise ValueError("site %s is only partly stored on this host" % app.site[:12])
    spec = appspec.validate(store.read(sid, "app.json"))
    if spec["runtime"] not in app.runtimes:
        raise ValueError("this host does not offer the %s runtime" % spec["runtime"])
    root = os.path.join(home.path, "appsites", "%s-v%d" % (sid, body["version"]))
    if not os.path.isdir(root):
        tmp = root + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        for rel in body["files"]:
            dest = os.path.normpath(os.path.join(tmp, rel))
            if not dest.startswith(tmp + os.sep):
                raise ValueError("unsafe path in site: %r" % rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(store.read(sid, rel))
            if rel == spec["run"][0]:
                os.chmod(dest, 0o755)
        os.rename(tmp, root)
    needs = spec["needs"]
    run = list(spec["run"])
    if "/" in run[0]:
        run[0] = "/app/" + run[0].lstrip("./")
    allow = needs["net"] if (needs["net"] and app.grant_net) else []
    out = App(app.name, run, cwd=root, access=app.access, net=bool(allow), ro=app.ro,
               env={}, seconds=min(app.seconds, needs["seconds"]), env_file=app.env_file, allow=allow,
               site=app.site, runtimes=app.runtimes)
    out.secrets = needs["secrets"]
    return out


def bwrap_argv(app, scratch, env):
    """The bubblewrap command line that confines one session. Pure function: easy to test."""
    b = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--clearenv"]
    if app.net and not app.allow:
        b.append("--share-net")
    for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/alternatives", "/etc/ld.so.cache", "/etc/localtime",
              "/etc/terminfo", "/lib/terminfo"):
        b += ["--ro-bind-try", p, p]
    if app.net:
        for p in ("/etc/ssl", "/etc/ca-certificates"):
            b += ["--ro-bind-try", p, p]
        if not app.allow:
            for p in ("/etc/resolv.conf", "/etc/hosts"):
                b += ["--ro-bind-try", p, p]
    for p in app.ro:
        b += ["--ro-bind", p, p]
    b += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", scratch, "/work"]
    chdir = "/work"
    if app.cwd:
        b += ["--ro-bind", os.path.abspath(app.cwd), "/app"]
        chdir = "/app"
    b += ["--chdir", chdir]
    cmd = app.cmd
    if app.allow:                                   # no network namespace sharing: egress only via the allowlist proxy
        b += ["--ro-bind", os.path.dirname(os.path.abspath(__file__)), "/alt"]
        proxy = "http://127.0.0.1:3128"
        env = dict(env, HTTPS_PROXY=proxy, https_proxy=proxy, ALL_PROXY=proxy, NO_PROXY="")
        cmd = ["sh", "-c", 'python3 /alt/netproxy.py /work/.proxy.sock 3128 & exec "$@"', "sh"] + app.cmd
    env = dict(env, HOME="/work", PATH="/usr/local/bin:/usr/bin:/bin", LANG="C.UTF-8")
    for k, v in env.items():
        b += ["--setenv", k, v]
    return b + ["--"] + cmd


def sandbox_available():
    """True if bubblewrap exists and can create a sandbox here (not just be installed)."""
    exe = shutil.which("bwrap")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "--unshare-all", "--ro-bind-try", "/usr", "/usr", "--ro-bind-try", "/bin", "/bin",
                            "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64", "true"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))


def _write_all(buf, data, alive):
    while data and alive():
        try:
            n = buf.write(data)
        except Exception:
            n = 0
        if n:
            data = data[n:]
            buf.flush()
        else:
            time.sleep(0.02)


class _Session:
    """One client: reads the header, picks and authorises the app, runs it in its own scratch dir."""
    def __init__(self, host, link):
        self.host, self.link = host, link
        self.inq = queue.Queue()
        self.remote = None
        self.proc = self.master = self.scratch = self.proxy = None
        self.closed = threading.Event()
        RNS = net._rns()
        self.buf = RNS.Buffer.create_bidirectional_buffer(0, 0, link.get_channel(), self.on_ready)
        link.set_remote_identified_callback(lambda l, ident: setattr(self, "remote", ident))
        link.set_link_closed_callback(lambda l: self.close())
        threading.Thread(target=self.run, daemon=True).start()

    def alive(self):
        return not self.closed.is_set() and self.link.status == net._rns().Link.ACTIVE

    def on_ready(self, n):
        data = self.buf.read(n)
        if data:
            self.inq.put(data)

    def say(self, text):
        _write_all(self.buf, text.replace("\n", "\r\n").encode(), self.alive)

    def read_line(self, echo=False, timeout=60):
        line, end = b"", time.time() + timeout
        while self.alive() and time.time() < end:
            try:
                data = self.inq.get(timeout=0.5)
            except queue.Empty:
                continue
            for k, c in enumerate(data):
                if c in (10, 13):
                    self.leftover = data[k + 1:]
                    return line
                if c in (8, 127):
                    line = line[:-1]
                    if echo:
                        self.say("\b \b")
                else:
                    line += bytes([c])
                    if echo:
                        _write_all(self.buf, bytes([c]), self.alive)
        return None

    def authorised(self, app):
        if app.access == "public":
            return True
        end = time.time() + 5                                   # the client's identify packet may trail the header
        while self.remote is None and time.time() < end and self.alive():
            time.sleep(0.1)
        return self.remote is not None and self.remote.hash.hex() in self.host.home.trusted()

    def run(self):
        try:
            self.leftover = b""
            line = self.read_line()
            if line is None or not line.startswith(HEADER):
                return self.finish("expected an Alternet app client")
            parts = line.split()
            try:
                rows, cols = max(5, min(int(parts[1]), 200)), max(20, min(int(parts[2]), 400))
                term = parts[3].decode() if len(parts) > 3 and parts[3].decode().replace("-", "").isalnum() else "xterm-256color"
                want = parts[4].decode() if len(parts) > 4 else ""
            except (IndexError, ValueError):
                rows, cols, term, want = 24, 80, "xterm-256color", ""
            apps = self.host.apps
            if not want and len(apps) == 1:
                want = next(iter(apps))
            if not want:
                self.say("Apps on this address:\n")
                names = sorted(apps)
                for i, n in enumerate(names, 1):
                    self.say("  %d) %-14s%s\n" % (i, n, "  (trusted peers only)" if apps[n].access == "trusted" else ""))
                self.say("Choose a number: ")
                pick = self.read_line(echo=True)
                self.say("\n")
                try:
                    want = names[int(pick) - 1]
                except (TypeError, ValueError, IndexError):
                    return self.finish("no such app")
            app = apps.get(want)
            if app is None:
                return self.finish("no app named %r here" % want)
            if not self.authorised(app):
                who = self.remote.hash.hex() if self.remote is not None else "unknown"
                net.log("refused %s for app %s" % (who, want))
                return self.finish("%s is for trusted peers only. Ask the host to run: alternet trust %s" % (want, who))
            if app.site:
                try:
                    app = resolve_site_app(self.host.home, app)
                except ValueError as e:
                    return self.finish("cannot start %s: %s" % (want, e))
            self.start(app, rows, cols, term)
            leftover, self.leftover = self.leftover, b""
            if leftover:
                self.feed(leftover)
            end = time.time() + app.seconds
            while self.alive() and time.time() < end and self.proc is not None and self.proc.poll() is None:
                try:
                    self.feed(self.inq.get(timeout=0.5))
                except queue.Empty:
                    pass
            if time.time() >= end:
                self.say("\n[session time limit reached]\n")
        finally:
            time.sleep(0.3)
            self.close()
            try:
                self.link.teardown()
            except Exception:
                pass

    def finish(self, msg):
        self.say(msg + "\n")
        time.sleep(0.3)

    def feed(self, data):
        if self.master is not None:
            try:
                os.write(self.master, data)
            except OSError:
                pass

    def start(self, app, rows, cols, term):
        import fcntl, pty, struct, termios
        self.scratch = tempfile.mkdtemp(prefix="s-", dir=self.host.scratch_root)
        os.chmod(self.scratch, 0o700)
        env = {"TERM": term, "LINES": str(rows), "COLUMNS": str(cols)}
        env.update(app.env)
        if app.env_file and os.path.exists(app.env_file):
            with open(app.env_file) as f:
                for ln in f:
                    k, eq, v = ln.strip().partition("=")
                    if eq and k and not k.startswith("#") and (app.secrets is None or k in app.secrets):
                        env[k] = v
        if self.host.sandbox:
            argv, run_env, cwd = bwrap_argv(app, self.scratch, env), None, None
        else:
            argv, run_env, cwd = app.cmd, dict(os.environ, HOME=self.scratch, **env), app.cwd or self.scratch
        if app.allow and self.host.sandbox:
            from .netproxy import AllowProxy
            self.proxy = AllowProxy(os.path.join(self.scratch, ".proxy.sock"), app.allow, net.log)
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, env=run_env,
                                     start_new_session=True, close_fds=True, preexec_fn=_limits)
        os.close(slave)
        net.log("app %s started (%dx%d, %s)" % (app.name, cols, rows, "sandboxed" if self.host.sandbox else "NO SANDBOX"))
        threading.Thread(target=self.pump, daemon=True).start()

    def pump(self):
        while self.alive():
            try:
                data = os.read(self.master, 4096)
            except OSError:
                break
            if not data:
                break
            _write_all(self.buf, data, self.alive)

    def close(self):
        self.closed.set()
        p, self.proc = self.proc, None
        if p is not None:
            if p.poll() is None:
                for sig in (signal.SIGHUP, signal.SIGKILL):
                    try:
                        os.killpg(p.pid, sig)
                    except OSError:
                        pass
                    try:
                        p.wait(timeout=2)
                        break
                    except Exception:
                        pass
            net.log("app session ended")
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None
        if self.proxy is not None:
            self.proxy.close()
            self.proxy = None
        if self.scratch:
            shutil.rmtree(self.scratch, ignore_errors=True)
            self.scratch = None


class Host:
    def __init__(self, home, apps, sandbox=True, max_sessions=4):
        self.home, self.apps, self.sandbox, self.max = home, apps, sandbox, max_sessions
        self.scratch_root = os.path.join(home.path, "sessions")
        shutil.rmtree(self.scratch_root, ignore_errors=True)       # leftovers from a crash
        os.makedirs(self.scratch_root, mode=0o700)
        self.sessions = []


def serve(home, apps, sandbox=True, max_sessions=4):
    """Announce the apps' address and run one sandboxed process per connecting client."""
    if not apps:
        raise SystemExit("alternet: no apps to serve (give a command after --, or create apps.json in %s)" % home.path)
    if sandbox and not sandbox_available():
        raise SystemExit("alternet: refusing to start: bubblewrap (bwrap) is missing or cannot create a sandbox here.\n"
                         "Install it (apt install bubblewrap) or, only for a machine you do not mind exposing, pass --no-sandbox.")
    RNS = net._rns()
    RNS.Reticulum(home.rns_dir, loglevel=int(os.environ.get("ALTERNET_LOGLEVEL", RNS.LOG_ERROR)))
    idfile = os.path.join(home.path, "app.identity")
    ident = RNS.Identity.from_file(idfile) if os.path.exists(idfile) else RNS.Identity()
    ident.to_file(idfile)
    dest = RNS.Destination(ident, RNS.Destination.IN, RNS.Destination.SINGLE, APP, ASPECT)
    host = Host(home, apps, sandbox, max_sessions)

    def on_link(link):
        host.sessions[:] = [s for s in host.sessions if not s.closed.is_set()]
        if len(host.sessions) >= host.max:
            net.log("app host busy, refusing a connection")
            link.teardown()
            return
        host.sessions.append(_Session(host, link))

    dest.set_link_established_callback(on_link)
    print("Serving %d app(s)%s:" % (len(apps), "" if sandbox else "  ** WITHOUT SANDBOX **"), flush=True)
    for a in apps.values():
        print("  %-14s %-8s %s" % (a.name, a.access, " ".join(a.cmd)), flush=True)
    print("Address: %s" % dest.hash.hex(), flush=True)
    print("Connect with: alternet open %s" % dest.hash.hex(), flush=True)
    start, last, burst = time.time(), time.time(), list(net.ANNOUNCE_BURST)
    while True:
        now = time.time()
        if burst and now - start >= burst[0]:        # early, repeated announces: the first can precede the link-up
            burst.pop(0); dest.announce(); last = now
        elif not burst and now - last >= 1800:
            dest.announce(); last = now
        time.sleep(1)


def app_address(home):
    RNS = net._rns()
    idfile = os.path.join(home.path, "app.identity")
    if not os.path.exists(idfile):
        return None
    return RNS.Destination.hash(RNS.Identity.from_file(idfile), APP, ASPECT).hex()


# ---------------------------------------------------------------- client
def connect(home, ref, timeout=30, retries=3):
    """Attach this terminal to the app at ADDRESS[/APP]. Ctrl-] disconnects."""
    import select, shutil as sh, termios, tty
    RNS = net._rns()
    addr_hex, _, appname = ref.partition("/")
    try:
        dh = bytes.fromhex(addr_hex)
        if len(dh) != 16:
            raise ValueError
    except ValueError:
        raise SystemExit("alternet: bad app address %r (expected 32 hex characters, optionally /APP)" % addr_hex)
    RNS.Reticulum(home.rns_dir, loglevel=int(os.environ.get("ALTERNET_LOGLEVEL", RNS.LOG_ERROR)))
    my_id = RNS.Identity.from_file(os.path.join(home.path, "node.identity")) if os.path.exists(
        os.path.join(home.path, "node.identity")) else None
    if my_id is None:
        net.node_ids(home)
        my_id = RNS.Identity.from_file(os.path.join(home.path, "node.identity"))
    print("Looking for the app ...", file=sys.stderr)
    link = None
    for attempt in range(retries):
        t = time.time()
        ident = RNS.Identity.recall(dh)
        while (ident is None or not RNS.Transport.has_path(dh)) and time.time() - t < timeout / 2:
            RNS.Transport.request_path(dh)
            time.sleep(1)
            ident = RNS.Identity.recall(dh)
        if ident is None:
            continue
        link = RNS.Link(RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP, ASPECT))
        t = time.time()
        while link.status != RNS.Link.ACTIVE and link.status != RNS.Link.CLOSED and time.time() - t < timeout / 2:
            time.sleep(0.1)
        if link.status == RNS.Link.ACTIVE:
            break
        link = None
    if link is None:
        raise SystemExit("alternet: could not reach %s (is it running, and are you connected to the network?)" % addr_hex)
    link.identify(my_id)
    out, filt = sys.stdout.buffer, OutputFilter()

    def on_ready(n):
        data = filt.feed(buf.read(n) or b"")
        if data:
            out.write(data)
            out.flush()

    buf = RNS.Buffer.create_bidirectional_buffer(0, 0, link.get_channel(), on_ready)
    size = sh.get_terminal_size(fallback=(80, 24))
    head = b"%s %d %d %s %s\n" % (HEADER, size.lines, size.columns,
                                  os.environ.get("TERM", "xterm-256color").encode(), appname.encode())
    _write_all(buf, head, lambda: True)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while link.status == RNS.Link.ACTIVE:
            if select.select([fd], [], [], 0.2)[0]:
                data = os.read(fd, 1024)
                if not data or ESCAPE in data:
                    break
                _write_all(buf, data, lambda: link.status == RNS.Link.ACTIVE)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        try:
            link.teardown()
        except Exception:
            pass
        sys.stdout.write("\033[0m\033[?25h\r\n[disconnected]\r\n")
