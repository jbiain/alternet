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
                conn.request("GET", "/bbs")
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



class FeedTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from alternet import crypto
        from alternet.feed import Feeds
        self.d = tempfile.mkdtemp()
        self.key = crypto.SigningKey.load_or_create(os.path.join(self.d, "k"))
        self.feeds = Feeds(os.path.join(self.d, "f"))

    def test_post_verify_and_order(self):
        from alternet import feed
        a = feed.make_entry(self.key, "room", "one", t=100)
        self.assertTrue(self.feeds.put(a))
        self.assertFalse(self.feeds.put(a))                       # idempotent
        b = feed.make_entry(self.key, "room", "two", self.feeds.heads("room"), t=101)
        self.feeds.put(b)
        self.assertEqual([e["body"]["text"] for _i, e in self.feeds.entries("room")], ["one", "two"])
        self.assertEqual(len(self.feeds.heads("room")), 1)

    def test_tamper_and_bad_input_rejected(self):
        from alternet import feed
        e = feed.make_entry(self.key, "room", "hello", t=100)
        e["body"]["text"] = "forged"
        with self.assertRaises(ValueError):
            self.feeds.put(e)
        for bad in ({}, {"body": 1, "sig": "00"}, {"body": e["body"], "sig": "zz"}):
            with self.assertRaises(ValueError):
                feed.verify_entry(bad)
        with self.assertRaises(ValueError):
            feed.make_entry(self.key, "../x", "hi")
        with self.assertRaises(ValueError):
            feed.make_entry(self.key, "room", "x" * 5000)
        far = feed.make_entry(self.key, "room", "future", t=10 ** 12)
        with self.assertRaises(ValueError):
            feed.verify_entry(far)
        other = feed.make_entry(self.key, "other", "x", t=1)
        with self.assertRaises(ValueError):
            feed.verify_entry(other, room="room")

    def test_merge_is_union_and_same_order_everywhere(self):
        import tempfile
        from alternet import feed
        from alternet.feed import Feeds
        es = [feed.make_entry(self.key, "r", "m%d" % i, t=100 + (i % 2)) for i in range(4)]
        f1, f2 = Feeds(os.path.join(self.d, "a")), Feeds(tempfile.mkdtemp())
        for e in es[:3]:
            f1.put(e)
        for e in es[1:]:
            f2.put(e)
        for e in es:
            f1.put(e); f2.put(e)
        self.assertEqual([i for i, _ in f1.entries("r")], [i for i, _ in f2.entries("r")])
        self.assertEqual(len(f1.ids("r")), 4)



class FeedBridgeTests(unittest.TestCase):
    def test_export_import_and_no_loops(self):
        import tempfile
        from alternet import feed
        from alternet.apphost import App, FeedBridge, shared_dir
        from alternet.home import Home
        h = Home(tempfile.mkdtemp()); h.init(standalone=True)
        app = App("room", ["x"], shared_mb=1, feed="lobby")
        d = shared_dir(h, app); os.makedirs(d)
        log = os.path.join(d, "room.log")
        with open(log, "w") as f:
            f.write(json.dumps({"t": 1, "n": "old", "m": "before start"}) + "\n")
        b = FeedBridge(h, app)
        b.step()
        self.assertEqual(h.feeds().ids("lobby"), [])                     # old lines are not exported
        with open(log, "a") as f:
            f.write(json.dumps({"t": 100, "n": "aa11bb", "m": "hello"}) + "\n")
            f.write(json.dumps({"t": 101, "n": "*", "m": "aa11bb joined"}) + "\n")
        b.step()
        es = h.feeds().entries("lobby")
        self.assertEqual([e["body"]["text"] for _i, e in es], ["<aa11bb> hello"])   # system lines stay local
        b.step(); b.step()
        self.assertEqual(len(h.feeds().ids("lobby")), 1)                  # no loop: imports are not re-exported
        from alternet import crypto
        other = crypto.SigningKey.load_or_create(os.path.join(tempfile.mkdtemp(), "k"))
        h.feeds().put(feed.make_entry(other, "lobby", "<zz> from afar", t=200))
        b.step(); b.step()
        lines = [json.loads(x) for x in open(log).read().splitlines()]
        self.assertEqual([x["m"] for x in lines if x.get("src")], ["<zz> from afar"])
        self.assertEqual(len(h.feeds().ids("lobby")), 2)                  # still no echo
        b2 = FeedBridge(h, app); b2.step()                                # restart: nothing is duplicated
        self.assertEqual(len([x for x in open(log).read().splitlines()]), 4)



class WebTermTests(unittest.TestCase):
    def test_target_validation(self):
        from alternet.webterm import TARGET
        a = "a" * 32
        for ok in (a, a + "/room", a + "@" + "b" * 32, a + "@" + "b" * 32 + "/x.y-z_1"):
            self.assertTrue(TARGET.match(ok), ok)
        for bad in ("", "abc", a + "/", a + "/../x", a + ";ls", a + "/a b", "A" * 32, a + "\n", "-h", a + "/" + "x" * 49):
            self.assertFalse(TARGET.match(bad), repr(bad))

    def test_names_resolve(self):
        import json as _j, tempfile
        from alternet.home import Home
        from alternet.webterm import resolve
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            a, b = "a" * 32, "b" * 32
            with open(d + "/webapps.json", "w") as f:
                _j.dump([{"name": "room", "address": a, "desc": "x"}], f)
            h.save_names({"blog": b})
            self.assertEqual(resolve(h, "room"), a)
            self.assertEqual(resolve(h, "Room/chat"), a + "/chat")
            self.assertEqual(resolve(h, "blog"), b)
            self.assertEqual(resolve(h, a), a)
            for bad in ("nope", "../x", "room;ls", "", "-h"):
                self.assertIsNone(resolve(h, bad), repr(bad))

    def test_words(self):
        from alternet import words
        self.assertEqual(len(set(words.WORDS)), 2048)
        a, b = "0123456789abcdef" * 2, "fedcba9876543210" * 2
        w = words.encode(a)
        self.assertRegex(w, r"^(\w{4}-){3}\w{4}$")
        self.assertEqual(words.matches(w, [a, b]), [a])
        self.assertEqual(words.matches(w.upper(), [a, b]), [a])
        self.assertEqual(words.matches("baka-baka-baka-baka", [a, b]), [])
        self.assertEqual(words.matches("room", [a]), [])
        twin = a[:11] + "0" * 21
        self.assertEqual(words.matches(w, [a, twin]), [a, twin])            # a collision is reported, never guessed

    def test_frames(self):
        import os as _os
        from alternet.webterm import _frame, _parse, MAX_FRAME
        def masked(op, data):
            m = _os.urandom(4)
            n = len(data)
            head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else b"\xfe" + n.to_bytes(2, "big"))
            return head + m + bytes(b ^ m[k % 4] for k, b in enumerate(data))
        for payload in (b"x", b"hello", b"y" * 300):
            op, data, rest = _parse(masked(2, payload) + b"tail")
            self.assertEqual((op, data, rest), (2, payload, b"tail"))
        self.assertIsNone(_parse(masked(2, b"hello")[:4]))                 # incomplete
        with self.assertRaises(ValueError):
            _parse(b"\x82\x05hello")                                     # unmasked client frame
        big = b"\x82\xff" + (MAX_FRAME + 1).to_bytes(8, "big") + b"\0" * 4
        with self.assertRaises(ValueError):
            _parse(big)
        f = _frame(b"z" * 200)
        self.assertEqual(f[:4], b"\x82\x7e\x00\xc8")


if __name__ == "__main__":
    unittest.main()


class TourTests(unittest.TestCase):
    def test_tour_runs_to_completion(self):
        from alternet import tour
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = tour.run(fast=True)
        self.assertEqual(rc, 0)
        self.assertIn("REJECTED", buf.getvalue())


class FancyBBSTests(unittest.TestCase):
    def test_fancy_runs_in_a_real_pty_with_address_bar(self):
        import pty, select, tempfile, time
        from alternet.home import Home
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            key = crypto.SigningKey.load_or_create(h.key_file)
            site = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples", "bbs-menu")
            m, blocks = sl.pack(site, key, "bbs", 1)
            for bh, blk in blocks.items():
                h.store().put_block(bh, blk)
            h.store().put_manifest(m)
            sid = m["body"]["site"]
            pid, fd = pty.fork()
            if pid == 0:
                os.environ["COLORTERM"] = "truecolor"; os.environ["TERM"] = "xterm-256color"
                os.execv(sys.executable, [sys.executable, "-m", "alternet", "--home", d, "bbs", sid, "--fancy"])
            seen = b""

            def pump(t=0.6):
                nonlocal seen
                end = time.time() + t
                while time.time() < end:
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if r:
                        try: seen += os.read(fd, 65536)
                        except OSError: return

            pump(1.5)
            os.write(fd, b"nosuchsite\r"); pump()      # the address bar has focus on landing: just type
            os.write(fd, b"\x1b[B"); pump()            # down-arrow moves focus to the menu
            os.write(fd, b"2"); pump(1.0)
            os.write(fd, b"b"); pump()
            os.write(fd, b"q"); pump(0.8)
            _, status = os.waitpid(pid, 0)
            import re
            text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", seen.decode("utf-8", "replace"))
            self.assertEqual(os.WEXITSTATUS(status), 0)
            self.assertIn("A L T E R N E T", text)
            self.assertIn("address", text)
            self.assertIn("unknown site", text)
            self.assertIn("Installing Alternet", text)


class GfxTests(unittest.TestCase):
    @staticmethod
    def _png(w, h, pixel):
        import struct, zlib
        raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
        def chunk(k, d):
            return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    def test_png_decodes_and_renders_halfblocks(self):
        from alternet import gfx
        data = self._png(4, 4, lambda x, y: (255, 0, 0) if y < 2 else (0, 0, 255))
        w, h, rows = gfx.decode_png(data)
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(rows[0][0], (255, 0, 0))
        self.assertEqual(rows[3][3], (0, 0, 255))
        lines = gfx.render_png(data, 10, 10)          # small images are scaled up to fill the box
        self.assertEqual(len(lines), 5)
        self.assertIn("▀", lines[0])

    def test_garbage_is_rejected(self):
        from alternet import gfx
        with self.assertRaises(ValueError):
            gfx.decode_png(b"not a png at all")

    def test_world_walls_block_and_doors_are_found(self):
        from alternet import world
        w = world.World([("one", "a" * 32), ("two", "b" * 32)])
        for _ in range(40):
            w.step(world.MOVE)                     # facing up from the start: must stop at the wall
        self.assertGreater(w.y, 1.0)
        self.assertEqual(w.cell(int(w.x), int(w.y)), ".")
        w.x, w.y, w.a = 1.5, 1.5, -3.14159 / 2     # just below door '1' on the top wall
        self.assertEqual(w.facing_door(), 0)
        frame = w.frame(60, 12)
        self.assertEqual(len(frame), 14)
        self.assertIn("one", frame[-2])

    def test_world_play_returns_the_chosen_door(self):
        from alternet import world
        w = world.World([("one", "a" * 32)])
        w.x, w.y, w.a = 1.5, 1.5, -3.14159 / 2
        keys = iter(["left", "right", "enter"])
        out = []
        ref = world.play(w, lambda t: next(keys), out.append, lambda: (60, 20))
        self.assertEqual(ref, "a" * 32)


class WorldPtyTests(unittest.TestCase):
    def test_world_command_runs_and_quits_in_a_pty(self):
        import pty, select, time, tempfile
        from alternet.home import Home
        with tempfile.TemporaryDirectory() as d:
            h = Home(d)
            h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
            names = {"home": "a" * 32}
            h.save_names(names)
            pid, fd = pty.fork()
            if pid == 0:
                os.environ["COLORTERM"] = "truecolor"; os.environ["TERM"] = "xterm-256color"
                os.execv(sys.executable, [sys.executable, "-m", "alternet", "--home", d, "world"])
            seen, end = b"", time.time() + 1.5
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    seen += os.read(fd, 65536)
            os.write(fd, b"\x1b[A"); time.sleep(0.4)
            os.write(fd, b"q")
            end = time.time() + 1.0
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    try: seen += os.read(fd, 65536)
                    except OSError: break
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
            self.assertIn("▀".encode(), seen)
            self.assertIn(b"walk up to a glowing door", seen)


class NameTests(unittest.TestCase):
    @staticmethod
    def _publish(home, key, pages, name, version):
        with tempfile.TemporaryDirectory() as d:
            for fn, text in pages.items():
                with open(os.path.join(d, fn), "w") as f:
                    f.write(text)
            m, blocks = sl.pack(d, key, name, version)
        for bh, blk in blocks.items():
            home.store().put_block(bh, blk)
        home.store().put_manifest(m)
        return m["body"]["site"]

    def _home(self, tmp):
        from alternet.home import Home
        h = Home(tmp)
        h.save_settings({"auto": False, "listen": [], "connect": [], "relay": False, "standalone": True, "trusted": []})
        return h

    def test_name_at_owner_tag_resolves_a_stored_site(self):
        from alternet import cli
        with tempfile.TemporaryDirectory() as tmp:
            h = self._home(tmp)
            alice = crypto.SigningKey.load_or_create(os.path.join(tmp, "alice.key"))
            bob = crypto.SigningKey.load_or_create(os.path.join(tmp, "bob.key"))
            sa = self._publish(h, alice, {"index.md": "a"}, "bbs", 1)
            sb = self._publish(h, bob, {"index.md": "b"}, "bbs", 1)
            tag_a = sl.owner_tag(alice.public_bytes().hex())
            self.assertEqual(cli._expand(h, "bbs@" + tag_a), sa)
            self.assertEqual(cli._expand(h, "bbs@" + sl.owner_tag(bob.public_bytes().hex())), sb)
            self.assertEqual(sl.display_name(h.store().info(sa)), "bbs@" + tag_a)
            node = "ab" * 16
            self.assertEqual(cli._expand(h, sa + "@" + node), sa + "@" + node)     # 32 hex = node address, untouched

    def test_directory_name_is_pinned_and_a_change_is_refused(self):
        from alternet import cli
        with tempfile.TemporaryDirectory() as tmp:
            h = self._home(tmp)
            owner = crypto.SigningKey.load_or_create(os.path.join(tmp, "o.key"))
            s1 = self._publish(h, owner, {"index.md": "one"}, "one", 1)
            s2 = self._publish(h, owner, {"index.md": "two"}, "two", 1)
            dsid = self._publish(h, owner, {"names.json": json.dumps({"hello": s1})}, "dir", 1)
            h.save_directories([dsid])
            self.assertEqual(cli._expand(h, "hello"), s1)
            self.assertEqual(h.name_pins()["hello"], s1)
            self._publish(h, owner, {"names.json": json.dumps({"hello": s2})}, "dir", 2)   # directory swaps the name
            with self.assertRaises(cli.NameChanged):
                cli._expand(h, "hello")
            pins = h.name_pins(); pins.pop("hello"); h.save_name_pins(pins)               # what `name unpin` does
            self.assertEqual(cli._expand(h, "hello"), s2)


class AppHostTests(unittest.TestCase):
    def test_filter_keeps_safe_and_drops_dangerous(self):
        from alternet.apphost import OutputFilter
        f = OutputFilter()
        safe = b"hi \x1b[1;31mred\x1b[0m \x1b[2J\x1b[H\x1b[?25l\x1b[?1049h\x1b(B"
        self.assertEqual(f.feed(safe), safe)
        for bad in (b"\x1b]52;c;aGVsbG8=\x07", b"\x1b]0;title\x1b\\", b"\x1b[6n", b"\x1b[c", b"\x1b[18t",
                    b"\x1bPq#0\x1b\\", b"\x1b_Gf=100;AAAA\x1b\\", b"\x1b[?1049;9001h"):
            self.assertEqual(OutputFilter().feed(b"a" + bad + b"b"), b"ab", bad)

    def test_filter_handles_split_sequences(self):
        from alternet.apphost import OutputFilter
        f = OutputFilter()
        out = f.feed(b"x\x1b]52;c;aGV") + f.feed(b"sbG8=\x07y\x1b[3") + f.feed(b"1mz\x1b[6") + f.feed(b"nq")
        self.assertEqual(out, b"xy\x1b[31mzq")

    def test_shared_dir_binding_and_quota(self):
        from alternet.apphost import App, bwrap_argv, shared_usage
        a = App("room", ["x"], shared_mb=2)
        argv = bwrap_argv(a, "/s", {}, shared="/h/shared/room")
        i = argv.index("/work/shared")
        self.assertEqual(argv[i - 2:i + 1], ["--bind", "/h/shared/room", "/work/shared"])
        self.assertEqual(bwrap_argv(a, "/s", {}, shared="/h/shared/room", shared_ro=True)[i - 2], "--ro-bind")
        self.assertNotIn("/work/shared", bwrap_argv(App("x", ["x"]), "/s", {}))
        self.assertEqual(App("x", ["x"]).shared_mb, 0)
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "f"), "wb") as f:
            f.write(b"x" * 1000)
        self.assertEqual(shared_usage(d), 1000)

    def test_bwrap_argv_confines_and_defaults_offline(self):
        from alternet.apphost import App, bwrap_argv
        a = App("chat", ["python3", "app.py"], cwd="/opt/apps/chat")
        argv = bwrap_argv(a, "/scratch/s1", {"TERM": "xterm"})
        self.assertIn("--unshare-all", argv)
        self.assertNotIn("--share-net", argv)
        self.assertIn("--clearenv", argv)
        i = argv.index("/app")
        self.assertEqual(argv[i - 2], "--ro-bind")                 # app dir is read-only
        self.assertEqual(argv[-2:], ["python3", "app.py"])
        self.assertIn("--share-net", bwrap_argv(App("x", ["x"], net=True), "/s", {}))

    def test_apps_config_and_access_flag(self):
        import json, tempfile
        from alternet.apphost import load_apps, App
        from alternet.home import Home
        h = Home(tempfile.mkdtemp())
        os.makedirs(h.path, exist_ok=True)
        json.dump({"apps": {"a": {"cmd": ["x"]}, "b": {"cmd": ["y"], "access": "trusted"}}},
                  open(os.path.join(h.path, "apps.json"), "w"))
        apps = load_apps(h)
        self.assertEqual((apps["a"].access, apps["b"].access), ("public", "trusted"))
        with self.assertRaises(ValueError):
            App("z", ["x"], access="everyone")


class NetProxyTests(unittest.TestCase):
    def _connect(self, allow, target):
        import socket, tempfile
        from alternet.netproxy import AllowProxy
        d = tempfile.mkdtemp()
        p = AllowProxy(os.path.join(d, "p.sock"), allow)
        try:
            c = socket.socket(socket.AF_UNIX)
            c.settimeout(10)
            c.connect(os.path.join(d, "p.sock"))
            c.sendall(("CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n" % (target, target)).encode())
            return c.recv(200).split(b"\r\n")[0]
        finally:
            p.close()

    def test_host_rules(self):
        from alternet.netproxy import host_allowed
        self.assertTrue(host_allowed("api.openai.com", ["api.openai.com"]))
        self.assertTrue(host_allowed("auth.openai.com", [".openai.com"]))
        self.assertFalse(host_allowed("evilopenai.com", [".openai.com"]))
        self.assertFalse(host_allowed("openai.com.evil.net", ["openai.com"]))

    def test_denies_unlisted_wrong_port_and_loopback(self):
        self.assertIn(b"403", self._connect(["api.openai.com"], "example.com:443"))
        self.assertIn(b"403", self._connect(["api.openai.com"], "api.openai.com:22"))
        self.assertIn(b"403", self._connect(["localhost"], "localhost:443"))      # allowlisted but not public
        self.assertIn(b"403", self._connect(["127.0.0.1"], "127.0.0.1:443"))

    def test_bwrap_allowlist_mode_has_no_shared_net(self):
        from alternet.apphost import App, bwrap_argv
        argv = bwrap_argv(App("c", ["codex"], net=True, allow=["api.openai.com"]), "/s", {})
        self.assertNotIn("--share-net", argv)
        self.assertIn("HTTPS_PROXY", argv)


class PageFmtTests(unittest.TestCase):
    def test_safe_calc(self):
        from alternet.pagefmt import evaluate
        v = {"a": "4", "b": "2.5"}
        self.assertEqual(evaluate("a * b + 1", v), 11.0)
        self.assertEqual(evaluate("max(a, 10) / 4", v), 2.5)
        self.assertIsNone(evaluate("__import__('os').system('x')", v))
        self.assertIsNone(evaluate("a.__class__", v))
        self.assertIsNone(evaluate("1/0", v))
        self.assertIsNone(evaluate("9**9**9", v))

    def test_blocks_and_render_with_image(self):
        import tempfile
        from alternet import pagefmt, site as sitelib, crypto
        text = "# T\n![logo](logo.png)\n:input n \"N\"\n:calc d \"Double\" = n * 2\nplain"
        bl = pagefmt.blocks(text.splitlines())
        self.assertEqual([b[0] for b in bl], ["text", "image", "input", "calc", "text"])
        self.assertEqual(pagefmt.fields(bl), [("input", "n")])
        d = tempfile.mkdtemp()
        src = os.path.join(d, "s"); os.makedirs(src)
        import shutil
        shutil.copy(os.path.join(os.path.dirname(__file__), "..", "examples", "bbs-menu", "logo.png"), src)
        open(os.path.join(src, "index.md"), "w").write(text)
        store = sitelib.Store(os.path.join(d, "store"))
        key = crypto.SigningKey.load_or_create(os.path.join(d, "k"))
        m, blocks = sitelib.pack(src, key, "t", 1)
        store.put_manifest(m)
        for h, data in blocks.items():
            store.put_block(h, data)
        sid = sitelib.verify_manifest(m)["site"]
        out = pagefmt.render(bl, {"n": "21"}, None, store, sid, 80)
        self.assertTrue(any("\x1b[38;2" in ln for ln in out))          # image drawn
        self.assertTrue(any("Double" in ln and "42" in ln for ln in out))


class StoreLimitTests(unittest.TestCase):
    def test_gc_drops_unpinned_oldest_only(self):
        import tempfile, time, subprocess
        d = tempfile.mkdtemp()
        env = dict(os.environ)
        def run(*a):
            return subprocess.run([sys.executable, "-m", "alternet", "--home", os.path.join(d, "h")] + list(a),
                                  capture_output=True, text=True, env=dict(env, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..")))
        run("init", "--no-auto", "--standalone")
        from alternet.home import Home
        from alternet import site as sitelib, crypto
        h = Home(os.path.join(d, "h")); st = h.store()
        sids = []
        for i in range(3):
            src = os.path.join(d, "s%d" % i); os.makedirs(src)
            open(os.path.join(src, "index.md"), "w").write("x" * 3000 + str(i))
            key = crypto.SigningKey.load_or_create(os.path.join(d, "k%d" % i))      # someone else's site
            m, blocks = sitelib.pack(src, key, "n%d" % i, 1)
            st.put_manifest(m)
            for bh, data in blocks.items():
                st.put_block(bh, data)
            sids.append(sitelib.verify_manifest(m)["site"])
            os.utime(st._m(sids[-1]), (time.time() - 100 + i, time.time() - 100 + i))
        self.assertTrue(all(st.complete(s) for s in sids))
        h.save_pins([sids[0]])                                  # oldest, but pinned
        r = run("gc", "--limit", "0.004")                       # room for about one site
        left = h.store().sites()
        self.assertIn(sids[0], left)                            # pinned: kept
        self.assertNotIn(sids[1], left)                         # oldest unpinned: dropped
        self.assertTrue(r.returncode == 0, r.stderr)


class RelayListTests(unittest.TestCase):
    def test_reads_relays_from_stored_landing_site(self):
        import tempfile, shutil
        from alternet import cli, site as sitelib, crypto
        from alternet.home import Home
        d = tempfile.mkdtemp(); h = Home(os.path.join(d, "h")); h.init(auto=False, standalone=True)
        src = os.path.join(d, "s"); os.makedirs(src)
        open(os.path.join(src, "index.md"), "w").write("x")
        open(os.path.join(src, "relays.txt"), "w").write("# c\na.example:4242\nbad line\nb.example:4243 # hi\na.example:4242\n")
        m, blocks = sitelib.pack(src, h.key(), "bbs", 1)
        st = h.store(); st.put_manifest(m)
        for bh, data in blocks.items():
            st.put_block(bh, data)
        sid = sitelib.verify_manifest(m)["site"]
        self.assertEqual(cli.relay_list(h, sid), ["a.example:4242", "b.example:4243"])


class AppSpecTests(unittest.TestCase):
    GOOD = {"app": 1, "title": "Codex", "run": ["codex", "--x"], "runtime": "native",
            "needs": {"secrets": ["OPENAI_API_KEY"], "net": ["api.openai.com", ".openai.com"], "storage_mb": 50, "seconds": 3600}}

    def test_valid(self):
        from alternet import appspec
        s = appspec.validate(self.GOOD)
        self.assertEqual(s["needs"]["secrets"], ["OPENAI_API_KEY"])
        self.assertEqual(appspec.validate({"app": 1, "title": "t", "run": ["x"]})["needs"]["net"], [])   # defaults: no net
        self.assertIn("OPENAI_API_KEY", "\n".join(appspec.describe(s)))

    def test_rejects_bad(self):
        import copy
        from alternet import appspec
        def bad(**kw):
            d = copy.deepcopy(self.GOOD); d.update(kw)
            with self.assertRaises(ValueError, msg=str(kw)):
                appspec.validate(d)
        bad(app=2); bad(title=""); bad(run=[]); bad(run=["/bin/sh"]); bad(run=["../x"]); bad(runtime="ruby")
        bad(extra=1); bad(needs={"root": True}); bad(needs={"net": ["127.0.0.1"]}); bad(needs={"net": ["*.x.com"]})
        bad(needs={"secrets": ["bad name"]}); bad(needs={"seconds": 1}); bad(needs={"storage_mb": -1})
        with self.assertRaises(ValueError):
            appspec.validate("not json")

    def test_publish_checks_run_path(self):
        import json, tempfile
        from alternet import appspec
        d = tempfile.mkdtemp()
        self.assertIsNone(appspec.check_site_dir(d))
        json.dump(dict(self.GOOD, run=["bin/app"]), open(os.path.join(d, "app.json"), "w"))
        with self.assertRaises(ValueError):
            appspec.check_site_dir(d)
        os.makedirs(os.path.join(d, "bin")); open(os.path.join(d, "bin", "app"), "w").write("x")
        self.assertEqual(appspec.check_site_dir(d)["run"], ["bin/app"])


class SiteAppTests(unittest.TestCase):
    def _store_app(self, spec, files):
        import json, tempfile
        from alternet import site as sitelib
        from alternet.home import Home
        d = tempfile.mkdtemp(); h = Home(os.path.join(d, "h")); h.init(auto=False, standalone=True)
        src = os.path.join(d, "s"); os.makedirs(src)
        open(os.path.join(src, "app.json"), "w").write(json.dumps(spec))
        for k, v in files.items():
            open(os.path.join(src, k), "w").write(v)
        m, blocks = sitelib.pack(src, h.key(), "demo", 1)
        st = h.store(); st.put_manifest(m)
        for bh, data in blocks.items():
            st.put_block(bh, data)
        return h, sitelib.verify_manifest(m)["site"]

    def test_resolves_stored_app_with_host_policy(self):
        from alternet.apphost import App, resolve_site_app
        h, sid = self._store_app({"app": 1, "title": "D", "run": ["python3", "main.py"], "runtime": "python3",
                                  "needs": {"net": ["api.example.com"], "secrets": ["K"], "seconds": 120}},
                                 {"main.py": "print(1)"})
        a = resolve_site_app(h, App("d", None, site=sid, access="trusted", seconds=900))
        self.assertEqual(a.cmd, ["python3", "main.py"])
        self.assertEqual((a.access, a.seconds, a.allow, a.net), ("trusted", 120, [], False))   # net not granted by host
        self.assertTrue(os.path.exists(os.path.join(a.cwd, "main.py")))
        self.assertEqual(a.secrets, ["K"])
        g = resolve_site_app(h, App("d", None, site=sid, grant_net=True))
        self.assertEqual(g.allow, ["api.example.com"])

    def test_refuses_unoffered_runtime_and_missing_site(self):
        from alternet.apphost import App, resolve_site_app
        h, sid = self._store_app({"app": 1, "title": "D", "run": ["x"], "runtime": "native"}, {})
        with self.assertRaises(ValueError):
            resolve_site_app(h, App("d", None, site=sid))                       # host only offers python3 by default
        with self.assertRaises(ValueError):
            resolve_site_app(h, App("d", None, site="0" * 32))


class SpecHandshakeTests(unittest.TestCase):
    def test_spec_line_roundtrip_and_tamper(self):
        import json
        from alternet.apphost import spec_line, parse_spec_line
        t = SiteAppTests("test_resolves_stored_app_with_host_policy")
        h, sid = t._store_app({"app": 1, "title": "D", "run": ["x"], "runtime": "python3",
                               "needs": {"secrets": ["K"]}}, {})
        line = spec_line(h.store(), sid)
        site, spec = parse_spec_line(line, sid)
        self.assertEqual((site, spec["needs"]["secrets"]), (sid, ["K"]))
        with self.assertRaises(ValueError):
            parse_spec_line(line, "f" * 32)                               # host offered a different site
        d = json.loads(line[8:])
        first = next(iter(d["blocks"]))
        import base64
        d["blocks"][first] = base64.b64encode(b'{"app":1,"title":"evil","run":["x"]}').decode()
        with self.assertRaises(ValueError):
            parse_spec_line(b"ALTSPEC " + json.dumps(d).encode() + b"\n", sid)   # block no longer matches its hash


class StorageSyncTests(unittest.TestCase):
    def test_pack_unpack_roundtrip_and_limits(self):
        import tempfile
        from alternet.apphost import pack_dir, unpack_dir
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        os.makedirs(os.path.join(a, "sub")); open(os.path.join(a, "sub", "x.txt"), "w").write("hello")
        os.symlink("/etc/passwd", os.path.join(a, "link"))                 # symlinks never travel
        blob = pack_dir(a, 1 << 20)
        self.assertEqual(unpack_dir(blob, b, 1 << 20), 1)
        self.assertEqual(open(os.path.join(b, "sub", "x.txt")).read(), "hello")
        with self.assertRaises(ValueError):
            pack_dir(a, 3)
        with self.assertRaises(ValueError):
            unpack_dir(blob, tempfile.mkdtemp(), 3)

    def test_unpack_rejects_hostile_paths(self):
        import base64, json, tempfile, zlib
        from alternet.apphost import unpack_dir
        for rel in ("../evil", "/abs", "a/../../b", "", "a//b", "a\\b"):
            blob = base64.b64encode(zlib.compress(json.dumps({"f": {rel: "eA=="}}).encode()))
            with self.assertRaises(ValueError, msg=rel):
                unpack_dir(blob, tempfile.mkdtemp(), 1 << 20)

    def test_demux_splits_text_and_payload_across_chunks(self):
        from alternet.apphost import Demux, SAVE
        d = Demux()
        stream = b"screen text" + SAVE + b"PAYLOAD\nafter"
        text, got = b"", None
        for i in range(0, len(stream), 4):                                  # worst case: tiny chunks
            t, p = d.feed(stream[i:i + 4])
            text += t
            got = got or p
        self.assertEqual((text, got), (b"screen textafter", b"PAYLOAD"))     # output after the save line still shows


class LocalRunTests(unittest.TestCase):
    def test_seatbelt_profile_denies_by_default(self):
        from alternet.localrun import seatbelt_profile
        p = seatbelt_profile(["/opt/app"], ["/tmp/scratch"], 4321)
        self.assertIn("(deny default)", p)
        self.assertIn('(subpath "/tmp/scratch")', p)
        self.assertIn("localhost:4321", p)
        self.assertNotIn("network*", p)                                   # no blanket network permission
        self.assertNotIn("localhost", seatbelt_profile([], [], None))      # no proxy: no network at all
        self.assertNotIn("/Users", p)                                      # home directory is never granted

    def test_data_bind_in_bwrap(self):
        from alternet.apphost import App, bwrap_argv
        argv = bwrap_argv(App("a", ["x"]), "/s", {}, data="/home/u/data")
        i = argv.index("/work/data")
        self.assertEqual((argv[i - 2], argv[i - 1]), ("--bind", "/home/u/data"))
