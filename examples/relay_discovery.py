#!/usr/bin/env python3
"""Regression test for the relay announce problem (see docs/005): through a relay, a reader that joins
MORE THAN A MINUTE after the publisher started must still discover the site from its announcements
(no SITEID@ADDRESS hint). Before the fix, relays silently stopped forwarding the publisher's announces after
about 48 seconds (Reticulum's per-destination announce rate limit) and late readers never found it.

Takes about 2.5 minutes.   Run:  python examples/relay_discovery.py   (exit code 0 = passed)
"""
import os, re, shutil, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY, ROOT = sys.executable, os.path.join(HERE, "..")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    tmp, procs = tempfile.mkdtemp(prefix="alternet-relay-"), []
    port = free_port()

    def cli(n, *a, timeout=150):
        return subprocess.run([PY, "-m", "alternet", "--home", os.path.join(tmp, n), *a], capture_output=True,
                              text=True, timeout=timeout, cwd=ROOT)

    def spawn(n, *a):
        p = subprocess.Popen([PY, "-m", "alternet", "--home", os.path.join(tmp, n), *a], cwd=ROOT,
                             stdout=open(os.path.join(tmp, n + ".log"), "w"), stderr=subprocess.STDOUT)
        procs.append(p)

    try:
        print("relay + publisher (default node settings)", flush=True)
        cli("R", "init", "--standalone", "--no-auto", "--relay"); cli("R", "listen", str(port))
        cli("P", "init", "--standalone", "--no-auto"); cli("P", "connect", "127.0.0.1:%d" % port)
        sid = re.search(r"Site ID: (\w+)", cli("P", "publish", os.path.join(HERE, "sample-site"), "--name", "alice").stdout).group(1)
        spawn("R", "node"); time.sleep(2); spawn("P", "node")
        t0 = time.time()
        for delay in (100, 130):
            time.sleep(max(0, t0 + delay - time.time()))
            n = "reader%d" % delay
            cli(n, "init", "--standalone", "--no-auto"); cli(n, "connect", "127.0.0.1:%d" % port)
            r = cli(n, "read", sid, "--wait", "50")          # NO address hint: discovery by announcement
            print("reader joining at ~%ds: exit=%d %s" % (delay, r.returncode, (r.stdout.strip() or r.stderr.strip())[:60]), flush=True)
            assert r.returncode == 0 and "Alice" in r.stdout, r.stderr
        print("\nPASSED"); return 0
    except Exception as e:
        print("\nFAILED:", repr(e)); return 1
    finally:
        for p in procs:
            if p.poll() is None: p.terminate()
        for p in procs:
            try: p.wait(5)
            except Exception: p.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
