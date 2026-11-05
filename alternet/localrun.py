"""Run an app site on YOUR machine (docs/014 step 6): the host never sees your data or keys.

`alternet run SITE` fetches the site (signature-verified), shows what the app asks for, and starts it inside
an OS sandbox: bubblewrap on Linux, sandbox-exec (Seatbelt) on macOS. Windows has no sandbox here, so it
refuses. The sandbox denies by default: the app can read the system and its own files, write only to a
scratch folder and its saved-data folder, and reach the network only through an allowlist proxy for the
hosts it declared. Output goes through the same escape-sequence filter as hosted apps."""
import os, shutil, signal, socket, subprocess, sys, tempfile, time
from . import apphost, appspec, net


def platform_sandbox():
    if sys.platform.startswith("linux") and shutil.which("bwrap") and apphost.sandbox_available():
        return "bwrap"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    return None


def _q(path):
    return '"%s"' % path.replace("\\", "\\\\").replace('"', '\\"')


def seatbelt_profile(read_paths, write_paths, proxy_port=None):
    """A deny-by-default Seatbelt profile. Pure function: easy to test."""
    p = ["(version 1)", "(deny default)",
         "(allow process-fork)", "(allow process-exec)", "(allow signal (target self))",
         "(allow sysctl-read)", "(allow mach-lookup)", "(allow ipc-posix-shm)",
         "(allow file-read-metadata)",
         '(allow file-read* (literal "/") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/System") '
         '(subpath "/Library") (subpath "/Applications") (subpath "/opt") (subpath "/private/etc") '
         '(subpath "/private/var/db") (subpath "/dev") (subpath "/etc"))',
         '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/tty") (regex #"^/dev/ttys[0-9]+$") '
         '(literal "/dev/ptmx") (literal "/dev/dtracehelper"))']
    for r in read_paths:
        p.append("(allow file-read* (subpath %s))" % _q(r))
    for w in write_paths:
        p.append("(allow file-read* file-write* (subpath %s))" % _q(w))
    if proxy_port:
        p.append('(allow network-outbound (remote ip "localhost:%d"))' % proxy_port)
    return "\n".join(p) + "\n"


def _real_prefixes(argv0, env_path):
    """Directories holding the interpreter/program the app will run (so a Homebrew/conda python is readable)."""
    exe = shutil.which(argv0, path=env_path) if "/" not in argv0 else argv0
    if not exe:
        return []
    real = os.path.realpath(exe)
    return list({os.path.dirname(os.path.dirname(real)), os.path.dirname(os.path.dirname(exe))})


def run(home, ref, timeout=30):
    import json, getpass, select, termios, tty, pty, fcntl, struct
    from .cli import _expand, _split_ref, NameChanged
    kind = platform_sandbox()
    if kind is None:
        raise SystemExit("alternet: no OS sandbox available here (needs bubblewrap on Linux or sandbox-exec on macOS), "
                         "so I will not run app code on this machine.")
    store = home.store()
    try:
        site, addr = _split_ref(_expand(home, ref))
    except NameChanged as e:
        raise SystemExit("alternet: %s" % e)
    sid = store.resolve(site) or (site.lower() if len(site) == 32 else None)
    if not sid:
        raise SystemExit("alternet: unknown site %r" % ref)
    body = store.info(sid)
    if not body or store.missing(body):
        print("Fetching %s ..." % sid[:12], file=sys.stderr)
        status, _ = net.fetch(home, sid, wait=timeout, hint=addr or None)
        body = store.info(sid)
        if not body or store.missing(body):
            raise SystemExit("alternet: could not fetch the site (is a peer connected?)")
    if "app.json" not in body["files"]:
        raise SystemExit("alternet: that site is not an app (it has no app.json)")
    try:
        spec = appspec.validate(store.read(sid, "app.json"))
    except ValueError as e:
        raise SystemExit("alternet: %s" % e)
    grants = home.app_grants()
    digest = apphost.spec_digest(spec)
    local_key = sid + ":local"
    if grants.get(local_key) != digest:
        print("\n".join(appspec.describe(spec)))
        print("  published by site %s (signature verified); it will run ON THIS MACHINE in a sandbox" % sid[:12])
        if input("Allow and run? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("alternet: not allowed, nothing was run")
        grants[local_key] = digest
        home.save_app_grants(grants)
    policy = apphost.App("local", None, site=sid, access="public", runtimes=appspec.RUNTIMES, grant_net=True)
    try:
        app = apphost.resolve_site_app(home, policy)
    except ValueError as e:
        raise SystemExit("alternet: %s" % e)
    env = {}
    for name in spec["needs"]["secrets"]:
        v = os.environ.get(name) or getpass.getpass("%s (stays on this machine): " % name)
        if v:
            env[name] = v
    size = shutil.get_terminal_size(fallback=(80, 24))
    env.update(TERM=os.environ.get("TERM", "xterm-256color"), LINES=str(size.lines), COLUMNS=str(size.columns))
    data = None
    if spec["needs"]["storage_mb"]:
        data = home.app_data_dir(sid)
        os.makedirs(data, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="alt-run-")
    proxy = listener = None
    try:
        if kind == "bwrap":
            if app.allow:
                from .netproxy import AllowProxy
                proxy = AllowProxy(os.path.join(scratch, ".proxy.sock"), app.allow, net.log)
            if data:
                env["ALTERNET_DATA"] = "/work/data"
            argv, cwd = apphost.bwrap_argv(app, scratch, env, data=data), None
            run_env = None
        else:
            port = None
            if app.allow:
                from .netproxy import AllowProxy
                listener = socket.socket()
                listener.bind(("127.0.0.1", 0))
                listener.listen(16)
                port = listener.getsockname()[1]
                proxy = AllowProxy(None, app.allow, net.log, listener=listener)
                pr = "http://127.0.0.1:%d" % port
                env.update(HTTPS_PROXY=pr, https_proxy=pr, ALL_PROXY=pr)
            tmp = os.path.join(scratch, "tmp")
            os.makedirs(tmp)
            real_scratch = os.path.realpath(scratch)
            writes = [real_scratch] + ([os.path.realpath(data)] if data else [])
            reads = [os.path.realpath(app.cwd)] + _real_prefixes(app.cmd[0], "/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""))
            prof = os.path.join(scratch, "profile.sb")
            with open(prof, "w") as f:
                f.write(seatbelt_profile(reads, writes, port))
            if data:
                env["ALTERNET_DATA"] = os.path.realpath(data)
            env.update(HOME=real_scratch, TMPDIR=tmp, PATH=os.environ.get("PATH", "/usr/bin:/bin"))
            cmd = list(app.cmd)
            exe = shutil.which(cmd[0], path=env["PATH"]) if "/" not in cmd[0] else cmd[0]
            if "/" in app.cmd[0] or (exe and exe.startswith(os.path.realpath(app.cwd))):
                pass
            if exe:
                cmd[0] = exe
            argv, cwd, run_env = ["sandbox-exec", "-f", prof] + cmd, os.path.realpath(app.cwd), env
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", size.lines, size.columns, 0, 0))
        proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, env=run_env,
                                start_new_session=True, close_fds=True)
        os.close(slave)
        filt = apphost.OutputFilter()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        end = time.time() + app.seconds
        try:
            tty.setraw(fd)
            while proc.poll() is None and time.time() < end:
                r, _, _ = select.select([fd, master], [], [], 0.3)
                if master in r:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    out = filt.feed(chunk)
                    if out:
                        sys.stdout.buffer.write(out)
                        sys.stdout.buffer.flush()
                if fd in r:
                    d = os.read(fd, 1024)
                    if not d or apphost.ESCAPE in d:
                        break
                    os.write(master, d)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            if proc.poll() is None:
                for sig in (signal.SIGHUP, signal.SIGKILL):
                    try:
                        os.killpg(proc.pid, sig)
                    except OSError:
                        pass
                    try:
                        proc.wait(timeout=2)
                        break
                    except Exception:
                        pass
            sys.stdout.write("\033[0m\033[?25h\r\n[finished]\r\n")
    finally:
        if proxy:
            proxy.close()
        shutil.rmtree(scratch, ignore_errors=True)
