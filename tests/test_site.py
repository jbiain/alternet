import json, os, sys, tempfile, threading, unittest, base64
from alternet import site as sl, crypto
from alternet.home import Home

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "examples", "sample-site")


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.key = crypto.SigningKey.load_or_create(os.path.join(self.tmp, "k"))
        self.m, self.blocks = sl.pack(SAMPLE, self.key, "alice", 1)

    def test_roundtrip_and_key_file_mode(self):
        self.assertEqual(sl.verify_manifest(self.m)["name"], "alice")
        self.assertEqual(oct(os.stat(os.path.join(self.tmp, "k")).st_mode & 0o777), "0o600")
        again = crypto.SigningKey.load_or_create(os.path.join(self.tmp, "k"))
        self.assertEqual(again.public_bytes(), self.key.public_bytes())

    def test_tamper_block(self):
        h, b = next(iter(self.blocks.items()))
        with self.assertRaises(ValueError):
            sl.verify_block(h, b[:-1] + bytes([b[-1] ^ 1]))

    def test_tamper_manifest_and_owner_swap(self):
        m2 = json.loads(json.dumps(self.m)); m2["body"]["version"] = 99
        with self.assertRaises(ValueError): sl.verify_manifest(m2)
        k2 = crypto.SigningKey.load_or_create(os.path.join(self.tmp, "k2"))
        m3 = json.loads(json.dumps(self.m)); m3["body"]["owner"] = k2.public_bytes().hex()
        with self.assertRaises(ValueError): sl.verify_manifest(m3)

    def test_malformed_manifest_is_valueerror(self):
        for bad in ({}, {"body": 1, "sig": "00"}, {"body": {}, "sig": "zz"}):
            with self.assertRaises(ValueError): sl.verify_manifest(bad)

    def test_rollback_rejected(self):
        s = sl.Store(os.path.join(self.tmp, "s")); s.put_manifest(self.m)
        with self.assertRaises(ValueError): s.put_manifest(self.m)

    def test_store_rejects_path_tricks(self):
        s = sl.Store(os.path.join(self.tmp, "s"))
        self.assertIsNone(s.get_block("../../etc/passwd"))
        self.assertIsNone(s.get_manifest("../x"))

    def test_bundle_roundtrip_and_tamper(self):
        src = sl.Store(os.path.join(self.tmp, "src")); src.put_manifest(self.m)
        for h, b in self.blocks.items(): src.put_block(h, b)
        sid = self.m["body"]["site"]; f = os.path.join(self.tmp, "x.altbundle")
        sl.export_bundle(src, sid, f)
        dst = sl.Store(os.path.join(self.tmp, "dst")); sl.import_bundle(dst, f)
        self.assertTrue(dst.read(sid, "index.md").startswith(b"# Alice"))
        bad = json.load(open(f)); k = next(iter(bad["blocks"]))
        raw = bytearray(base64.b64decode(bad["blocks"][k])); raw[0] ^= 1
        bad["blocks"][k] = base64.b64encode(bytes(raw)).decode(); json.dump(bad, open(f, "w"))
        with self.assertRaises(ValueError): sl.import_bundle(sl.Store(os.path.join(self.tmp, "d2")), f)
        self.assertEqual(sl.Store(os.path.join(self.tmp, "d2")).sites(), [])   # nothing stored


class AccessTests(unittest.TestCase):
    def test_private_flag_is_signed_and_blocks_are_marked(self):
        tmp = tempfile.mkdtemp()
        key = crypto.SigningKey.load_or_create(os.path.join(tmp, "k"))
        m, blocks = sl.pack(SAMPLE, key, "p", 1, access="private")
        self.assertEqual(sl.verify_manifest(m)["access"], "private")
        flipped = json.loads(json.dumps(m)); flipped["body"]["access"] = "public"   # attacker flips it
        with self.assertRaises(ValueError): sl.verify_manifest(flipped)
        s = sl.Store(os.path.join(tmp, "s")); s.put_manifest(m)
        for h, b in blocks.items(): s.put_block(h, b)
        sid = m["body"]["site"]
        self.assertTrue(s.is_private(sid))
        self.assertTrue(all(s.block_is_private(h) for h in blocks))
        self.assertFalse(s.block_is_private("0" * 64))
        with self.assertRaises(ValueError): sl.pack(SAMPLE, key, "p", 2, access="secret")


class PureCryptoInterop(unittest.TestCase):
    def test_pure_python_backend_matches(self):
        import subprocess, sys
        code = ("import sys,json;from alternet import crypto,site as s;"
                "k=crypto.SigningKey.load_or_create(sys.argv[1]);m,_=s.pack(sys.argv[2],k,'x',1);print(json.dumps(m))")
        env = dict(os.environ, ALT_PURE="1")
        kf = os.path.join(tempfile.mkdtemp(), "k")
        out = subprocess.run([sys.executable, "-c", code, kf, SAMPLE], env=env, capture_output=True, text=True, check=True).stdout
        self.assertEqual(sl.verify_manifest(json.loads(out))["name"], "x")   # signed by pure, verified here


class PetnameTests(unittest.TestCase):
    def test_expand_and_validation(self):
        import tempfile
        from alternet import cli
        from alternet.home import Home
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            sid, addr = "a" * 32, "b" * 32
            h.save_names({"blog": sid})
            self.assertEqual(cli._expand(h, "blog"), sid)
            self.assertEqual(cli._expand(h, "Blog@" + addr), sid + "@" + addr)
            self.assertEqual(cli._expand(h, "other"), "other")
            self.assertEqual(cli._expand(h, sid), sid)


class GatewayTests(unittest.TestCase):
    def test_serves_public_hides_private(self):
        import http.client, tempfile
        from alternet import gateway
        from alternet.home import Home
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            store = h.store()
            key = crypto.SigningKey.load_or_create(h.key_file)
            pub, pub_blocks = sl.pack(SAMPLE, key, "pub", 1, access="public")
            for bh, blk in pub_blocks.items():
                store.put_block(bh, blk)
            store.put_manifest(pub)
            priv, priv_blocks = sl.pack(SAMPLE, key, "priv", 1, access="private")
            for bh, blk in priv_blocks.items():
                store.put_block(bh, blk)
            store.put_manifest(priv)
            srv = gateway.serve(h, port=0, with_network=False)
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                port = srv.server_address[1]
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/")
                r = conn.getresponse()
                body = r.read().decode()
                self.assertIn(pub["body"]["site"], body)
                self.assertNotIn(priv["body"]["site"], body)
                conn.request("GET", "/s/%s/" % priv["body"]["site"])
                r = conn.getresponse()
                self.assertEqual(r.status, 404)
                r.read()
                conn.request("GET", "/s/%s/index.md" % pub["body"]["site"])
                r = conn.getresponse()
                body = r.read().decode()
                self.assertIn('<a href="/s/%s/about.txt">about.txt</a>' % pub["body"]["site"], body)
            finally:
                srv.shutdown()

    def test_inline_markdown_links_resolve_within_the_site(self):
        from alternet import gateway
        sid = "a" * 32
        rendered = gateway._render_md("See [the about page](about.txt) and `alternet read`.", sid)
        self.assertIn('<a href="/s/%s/about.txt">the about page</a>' % sid, rendered)
        self.assertIn("<code>alternet read</code>", rendered)


class BBSMenuTests(unittest.TestCase):
    def test_parses_numbered_links_as_menu_items(self):
        from alternet.tui import _parse
        text = ("# Title\n\n1. [About](about.md) - the about page\n2. [Install](install.md)\n"
                "Not a menu line.\n")
        items, lines = _parse(text)
        self.assertEqual(items, [("About", "about.md", "the about page"), ("Install", "install.md", "")])
        self.assertIn("# Title", lines)
        self.assertIn("Not a menu line.", lines)


class PlainBBSTests(unittest.TestCase):
    def test_plain_fallback_navigates_without_curses(self):
        import io, contextlib, tempfile
        from alternet.home import Home
        from alternet import tui, cli

        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            store = h.store()
            key = crypto.SigningKey.load_or_create(h.key_file)
            SITE = os.path.join(HERE := os.path.dirname(os.path.abspath(__file__)), "..", "examples", "bbs-menu")
            m, blocks = sl.pack(SITE, key, "bbs", 1)
            for bh, blk in blocks.items():
                store.put_block(bh, blk)
            store.put_manifest(m)
            sid = m["body"]["site"]

            inputs = iter(["2", "b", "q"])

            def fake_input(prompt=""):
                return next(inputs)

            buf = io.StringIO()
            import builtins
            real_input = builtins.input
            builtins.input = fake_input
            try:
                with contextlib.redirect_stdout(buf):
                    tui.run(h, sid, force_plain=True)
            finally:
                builtins.input = real_input
            out = buf.getvalue()
            self.assertIn("Installing Alternet", out)
            self.assertIn("ALTERNET BBS", out)


class RawAnsiKeyTests(unittest.TestCase):
    def test_getkey_decodes_arrow_escape_sequences(self):
        import io, tempfile
        from alternet.home import Home
        from alternet import tui

        if not tui.HAVE_RAWTTY:
            self.skipTest("termios/tty not available on this platform")
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            browser = tui.RawAnsiBrowser(tui.Nav(h))
        # Feed raw bytes through a pipe standing in for stdin, bypassing any terminal device.
        r, w = os.pipe()
        os.write(w, b"\x1b[B")
        real_stdin = sys.stdin
        try:
            sys.stdin = os.fdopen(r, "rb", buffering=0)
            self.assertEqual(browser._getkey(), "down")
        finally:
            sys.stdin = real_stdin
            os.close(w)


class SharedDirectoryTests(unittest.TestCase):
    def test_a_name_published_by_one_node_resolves_on_another(self):
        import tempfile, subprocess
        PY = sys.executable
        ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

        def run(home, *args):
            r = subprocess.run([PY, "-m", "alternet", "--home", home, *args], capture_output=True,
                               text=True, timeout=60, cwd=ROOT)
            return r.stdout

        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            run(a, "init", "--no-auto", "--standalone")
            run(b, "init", "--no-auto", "--standalone")
            run(a, "publish", os.path.join(ROOT, "examples", "sample-site"), "--name", "mysite", "--list")
            sid = run(a, "sites").split()[0]
            dirdir = os.path.join(tmp, "dircontent")
            os.makedirs(dirdir)
            with open(os.path.join(dirdir, "names.json"), "w") as f:
                json.dump({"hello": sid}, f)
            run(a, "publish", dirdir, "--name", "mydir")
            dsid = [l.split()[0] for l in run(a, "sites").splitlines() if "mydir" in l][0]
            bundle_d, bundle_s = os.path.join(tmp, "d.altbundle"), os.path.join(tmp, "s.altbundle")
            run(a, "export", dsid, bundle_d)
            run(a, "export", sid, bundle_s)
            run(b, "import", bundle_d)
            run(b, "import", bundle_s)
            run(b, "directory", "add", dsid)
            out = run(b, "read", "hello", "--offline")
            self.assertIn("Alice's board", out)


if __name__ == "__main__":
    unittest.main()
