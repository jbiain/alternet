#!/usr/bin/env python3
"""Demo / integration test on ONE machine: Proof 01 + Proof 03 + update propagation.

  A  publishes a site and serves it
  B  pins it from A (a replica), listening for C
  C  connects only to B and reads the site
  A  publishes version 2 -> B updates itself
  A  is killed -> a fresh node D still reads version 2 from B

Run:  python examples/three_nodes.py        (exit code 0 = all steps passed)
"""
import os, shutil, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Demo:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="alternet-demo-")
        self.procs = []

    def cli(self, name, *args, timeout=120):
        r = subprocess.run([PY, "-m", "alternet", "--home", os.path.join(self.tmp, name), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def spawn(self, name, *args):
        log = open(os.path.join(self.tmp, name + ".log"), "w")
        p = subprocess.Popen([PY, "-m", "alternet", "--home", os.path.join(self.tmp, name), *args],
                             stdout=log, stderr=subprocess.STDOUT)
        self.procs.append(p)
        return p

    def wait(self, what, cond, timeout=90):
        t = time.time()
        while time.time() - t < timeout:
            if cond():
                return True
            time.sleep(1)
        raise AssertionError("timed out waiting for " + what)

    def close(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try: p.wait(5)
            except Exception: p.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


def step(msg): print("\n== " + msg, flush=True)


def main():
    d = Demo()
    pa, pb = free_port(), free_port()
    try:
        site1 = os.path.join(d.tmp, "site"); shutil.copytree(os.path.join(HERE, "sample-site"), site1)
        step("A: init, publish v1, run node")
        d.cli("A", "init", "--standalone", "--no-auto"); d.cli("A", "listen", str(pa))
        rc, out, _ = d.cli("A", "publish", site1, "--name", "alice"); print(out.strip())
        sid = [l for l in out.splitlines() if l.startswith("Site ID:")][0].split()[-1]
        d.spawn("A", "node", "--interval", "3")

        step("B: init, connect to A, pin the site, run node (replica)")
        d.cli("B", "init", "--standalone", "--no-auto", "--relay")
        d.cli("B", "connect", "127.0.0.1:%d" % pa); d.cli("B", "listen", str(pb)); d.cli("B", "pin", sid)
        d.spawn("B", "node", "--interval", "3")
        d.wait("B to replicate v1", lambda: "v1" in d.cli("B", "sites")[1])
        print(d.cli("B", "sites")[1].strip())

        step("C: connects only to B and reads  (Proof 01 pattern)")
        d.cli("C", "init", "--standalone", "--no-auto"); d.cli("C", "connect", "127.0.0.1:%d" % pb)
        rc, out, err = d.cli("C", "read", sid, "--wait", "40")
        print(out.strip()); assert rc == 0 and "Alice" in out, err

        step("A: publish v2 -> B should update automatically")
        open(os.path.join(site1, "index.md"), "a").write("\nUpdate: version 2 is live.\n")
        print(d.cli("A", "publish", site1, "--name", "alice")[1].strip())
        d.wait("B to update to v2", lambda: "v2" in d.cli("B", "sites")[1])
        print(d.cli("B", "sites")[1].strip())

        step("Kill A. A fresh node D reads v2 from B  (Proof 03)")
        d.procs[0].terminate(); d.procs[0].wait(10)
        d.cli("D", "init", "--standalone", "--no-auto"); d.cli("D", "connect", "127.0.0.1:%d" % pb)
        rc, out, err = d.cli("D", "read", sid, "--wait", "40")
        print(out.strip()); assert rc == 0 and "version 2 is live" in out, err

        step("Tamper check: a corrupted bundle is rejected")
        d.cli("D", "export", sid, os.path.join(d.tmp, "x.altbundle"))
        import json, base64
        b = json.load(open(os.path.join(d.tmp, "x.altbundle"))); k = next(iter(b["blocks"]))
        raw = bytearray(base64.b64decode(b["blocks"][k])); raw[0] ^= 1; b["blocks"][k] = base64.b64encode(bytes(raw)).decode()
        with open(os.path.join(d.tmp, "bad.altbundle"), "w") as f:
            json.dump(b, f)
        d.cli("E", "init", "--standalone", "--no-auto")
        rc, out, err = d.cli("E", "import", os.path.join(d.tmp, "bad.altbundle")); print(err.strip())
        assert rc != 0 and "rejected" in err

        print("\nALL STEPS PASSED")
        return 0
    except Exception as e:
        print("\nFAILED:", repr(e))
        for n in ("A", "B"):
            lp = os.path.join(d.tmp, n + ".log")
            if os.path.exists(lp):
                print("--- %s.log ---\n%s" % (n, open(lp).read()[-1500:]))
        return 1
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main())
