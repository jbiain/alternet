#!/usr/bin/env python3
"""Demo / integration test: the trusted-peers allowlist (private sites).

  A publishes a PUBLIC site and a PRIVATE site, trusts only B.
  B (trusted)   reads both.        C (not trusted) reads the public site but NOT the private one.
  C cannot fetch a private block even if it knows the block hash.
  After A runs `untrust B`, B is refused too.
Run:  python examples/private_site.py        (exit code 0 = all steps passed)
"""
import os, re, shutil, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ROOT = os.path.join(HERE, "..")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Demo:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="alternet-priv-"); self.procs = []

    def home(self, n): return os.path.join(self.tmp, n)

    def cli(self, n, *args, timeout=120):
        r = subprocess.run([PY, "-m", "alternet", "--home", self.home(n), *args], capture_output=True,
                           text=True, timeout=timeout, cwd=ROOT)
        return r.returncode, r.stdout, r.stderr

    def spawn(self, n, *args):
        p = subprocess.Popen([PY, "-m", "alternet", "--home", self.home(n), *args], cwd=ROOT,
                             stdout=open(os.path.join(self.tmp, n + ".log"), "w"), stderr=subprocess.STDOUT)
        self.procs.append(p); return p

    def raw(self, n, port, addr, path, data):
        """Ask holder `addr` for /manifest or /block directly; prints GOT or DENIED."""
        code = ("import sys,time;from alternet.home import Home;from alternet import net;"
                "s=net.Session(Home(sys.argv[1]));time.sleep(3);ok=s.add_hint('x'*32,sys.argv[2],10);"
                "d=list(s.listener.seen['x'*32].items())[0] if ok else None;"
                "r=s._request(d[1][0],d[0],sys.argv[3],sys.argv[4].encode(),timeout=15) if d else None;"
                "print('GOT' if r else 'DENIED')")
        r = subprocess.run([PY, "-c", code, self.home(n), addr, path, data], capture_output=True, text=True,
                           timeout=90, cwd=ROOT)
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ERROR " + r.stderr[-300:]

    def close(self):
        for p in self.procs:
            if p.poll() is None: p.terminate()
        for p in self.procs:
            try: p.wait(5)
            except Exception: p.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


def step(m): print("\n== " + m, flush=True)
def field(out, name): return re.search(name + r":\s+([0-9a-f]{32})", out).group(1)


def main():
    d = Demo(); port = free_port(); conn = "127.0.0.1:%d" % port
    try:
        step("A: publish a public and a private site, run node")
        d.cli("A", "init", "--standalone", "--no-auto"); d.cli("A", "listen", str(port))
        out = d.cli("A", "publish", os.path.join(HERE, "sample-site"), "--name", "open")[1]
        pub = re.search(r"Site ID: (\w+)", out).group(1)
        out = d.cli("A", "publish", os.path.join(HERE, "private-site"), "--name", "secret", "--private")[1]
        sec = re.search(r"Site ID: (\w+)", out).group(1); print(out.strip())
        a_addr = field(d.cli("A", "address")[1], "node address")
        d.spawn("A", "node", "--interval", "3")

        step("B and C: init, connect to A, note peer ids; A trusts only B")
        ids = {}
        for n in "BC":
            d.cli(n, "init", "--standalone", "--no-auto"); d.cli(n, "connect", conn)
            ids[n] = field(d.cli(n, "address")[1], "peer id")
        print("B peer id", ids["B"], "| C peer id", ids["C"])
        d.cli("A", "trust", ids["B"]); print(d.cli("A", "trusted")[1].strip())

        step("B (trusted) reads the private site")
        rc, o, e = d.cli("B", "read", sec + "@" + a_addr, "--wait", "30"); print(o.strip())
        assert rc == 0 and "Only trusted peers" in o, e

        step("C (not trusted) reads the PUBLIC site by announce  -> allowed")
        rc, o, e = d.cli("C", "read", pub, "--wait", "30"); print(o.strip()[:60])
        assert rc == 0 and "Alice" in o, e

        step("C tries the PRIVATE site  -> refused, nothing stored")
        rc, o, e = d.cli("C", "read", sec + "@" + a_addr, "--wait", "20"); print(e.strip())
        assert rc != 0 and "Only trusted" not in o
        assert sec not in d.cli("C", "sites")[1], "private site leaked into C's store"

        step("C asks for a private BLOCK directly, knowing its hash  -> refused")
        import json
        m = json.load(open(os.path.join(d.home("A"), "store", "manifests", sec + ".json")))
        blk = m["body"]["files"]["index.md"][0]
        res = d.raw("C", port, a_addr, "/block", blk); print("C ->", res); assert res == "DENIED", res
        res = d.raw("B", port, a_addr, "/block", blk); print("B ->", res); assert res == "GOT", res

        step("A untrusts B  -> B is refused too")
        d.cli("A", "untrust", ids["B"])
        res = d.raw("B", port, a_addr, "/block", blk); print("B ->", res); assert res == "DENIED", res

        step("Private sites are not announced")
        assert sec not in d.cli("C", "sites")[1]
        print("\nALL STEPS PASSED"); return 0
    except Exception as e:
        print("\nFAILED:", repr(e))
        lp = os.path.join(d.tmp, "A.log")
        if os.path.exists(lp): print("--- A.log ---\n" + open(lp).read()[-1500:])
        return 1
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main())
