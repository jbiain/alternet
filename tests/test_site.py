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


class PixelUITests(unittest.TestCase):
    def test_canvas_png_roundtrips_and_text_draws(self):
        from alternet import canvas, gfx
        c = canvas.Canvas(60, 20, (0, 0, 0))
        c.text(2, 2, "Hi", (255, 255, 255), 2)
        w, h, rows = gfx.decode_png(c.png())
        self.assertEqual((w, h), (60, 20))
        self.assertTrue(any(px == (255, 255, 255) for row in rows for px in row))

    def test_image_protocol_encoding(self):
        from alternet import canvas
        png = canvas.Canvas(4, 4).png()
        self.assertTrue(canvas.encode_image(png, "kitty", 10, 5).startswith("\033_Ga=T,f=100"))
        self.assertTrue(canvas.encode_image(png, "iterm", 10, 5).startswith("\033]1337;File=inline=1"))
        self.assertIsNone(canvas.detect_protocol("none"))
        self.assertEqual(canvas.detect_protocol("kitty"), "kitty")

    def test_pixel_frame_has_clickable_regions(self):
        from alternet import tui
        items = [("a", "a.md", "first"), ("b", "b.md", "second")]
        c, hits = tui.pixel_frame("a" * 32, "index.md", items, ["# T"], 0, None, "ok", 960, 464)
        acts = [h[4] for h in hits]
        for want in (("back",), ("world",), ("addr",), ("item", 0), ("item", 1)):
            self.assertIn(want, acts)

    def test_mouse_report_parses_to_a_click(self):
        import io
        from alternet import tui
        r, w = os.pipe()
        os.write(w, b"\x1b[<0;12;7M")
        saved = sys.stdin
        sys.stdin = os.fdopen(r, "rb", buffering=0)
        try:
            self.assertEqual(tui.RawAnsiBrowser(None)._getkey(), ("click", 12, 7))
        finally:
            sys.stdin.close(); sys.stdin = saved; os.close(w)

    def test_pixel_mode_in_a_real_pty_with_mouse_click(self):
        import pty, select, tempfile, time, struct, fcntl, termios
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
                os.environ["ALTERNET_PIXEL"] = "iterm"; os.environ["TERM"] = "xterm-256color"
                os.execv(sys.executable, [sys.executable, "-m", "alternet", "--home", d, "bbs", sid, "--pixel"])
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
            seen = b""

            def pump(t=0.8):
                nonlocal seen
                end = time.time() + t
                while time.time() < end:
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if r:
                        try: seen += os.read(fd, 1 << 20)
                        except OSError: return

            pump(2.0)
            n_before = seen.count(b"]1337;File=inline=1")
            os.write(fd, b"\x1b[B"); pump()                     # menu focus -> repaint
            os.write(fd, b"\x1b[<0;40;9M"); pump(1.0)           # click inside the window area
            os.write(fd, b"q"); pump(0.8)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
            self.assertGreaterEqual(n_before, 1)
            self.assertGreater(seen.count(b"]1337;File=inline=1"), n_before)

    def test_click_coordinates_map_to_the_right_button(self):
        from alternet import tui
        items = [("a", "a.md", "first")]
        b = tui.PixelBrowser(None, "iterm")
        c, b._hits = tui.pixel_frame("a" * 32, "index.md", items, ["x"], 0, None, "ok", 960, 464)
        b._dims = (960, 464, 100, 29)
        self.assertEqual(b._hit(93, 1), ("world",))       # the 3D button, top right
        self.assertEqual(b._hit(5, 4), ("addr",))         # the address field


class ProbeTests(unittest.TestCase):
    def test_parse_probe(self):
        from alternet import canvas
        self.assertEqual(canvas.parse_probe(b"\x1b_Gi=31;OK\x1b\\\x1b[?62;c"), "kitty")
        self.assertEqual(canvas.parse_probe(b"\x1bP>|iTerm2 3.5\x1b\\\x1b[?62;4;c"), "iterm")
        self.assertEqual(canvas.parse_probe(b"\x1bP>|xterm.js(5.5)\x1b\\\x1b[?62;4;c"), "iterm")
        self.assertIsNone(canvas.parse_probe(b"\x1bP>|xterm.js(5.5)\x1b\\\x1b[?62;c"))   # images switched off
        self.assertIsNone(canvas.parse_probe(b"\x1b[?1;2c"))                              # plain terminal
        self.assertIsNone(canvas.parse_probe(b""))

    def test_pixel_flag_falls_back_instead_of_going_blank(self):
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
            pid, fd = pty.fork()
            if pid == 0:
                os.environ.pop("ALTERNET_PIXEL", None)
                os.environ["TERM"] = "xterm-256color"; os.environ["COLORTERM"] = "truecolor"
                os.execv(sys.executable, [sys.executable, "-m", "alternet", "--home", d, "bbs", m["body"]["site"], "--pixel"])
            seen = b""

            def pump(t):
                nonlocal seen
                end = time.time() + t
                while time.time() < end:
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if r:
                        try: seen += os.read(fd, 1 << 20)
                        except OSError: return

            pump(2.5)                 # nobody answers the terminal probe: must fall back, not stay blank
            os.write(fd, b"\x1b[B"); pump(0.3)      # the address bar has focus first; down-arrow leaves it
            os.write(fd, b"q"); pump(0.8)
            for _ in range(50):
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
                time.sleep(0.1)
            else:
                os.kill(pid, 9); os.waitpid(pid, 0)
                self.fail("did not exit")
            self.assertEqual(os.WEXITSTATUS(status), 0)
            self.assertIn(b"did not say it can show images", seen)
            self.assertIn("A L T E R N E T".encode(), __import__("re").sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", seen))
