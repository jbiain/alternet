"""A BBS-style terminal browser: a boxed menu, numbers (or arrow keys where available) to pick an item,
Enter to open it, 'b' to go back, 'q' to quit. Reads from the local Store (verified content only) and
fetches over the network on demand, the same way `alternet read` does. No new content format: a page is
just Markdown, and a line that looks like `N. [label](target)  - description` becomes a selectable menu
item; anything else is shown as text.

Two renderers share the same navigation (`Nav`): a full-screen `curses` one, and a plain print()/input()
one for terminals with no curses support (notably a-Shell on iOS, which ships no `_curses` module at all —
that's a platform gap, not something installable). `run()` picks whichever is available. The plain one is
also just how real dial-up BBSes looked: no full-screen redraw, type a number, press Enter.
"""
import re, shutil, sys, textwrap

try:
    import curses
    HAVE_CURSES = True
except ImportError:
    HAVE_CURSES = False

try:
    import termios, tty
    HAVE_RAWTTY = True
except ImportError:
    HAVE_RAWTTY = False

LINK = re.compile(r"^\s*\d+\.\s*\[([^\]]+)\]\(([^)\s]+)\)\s*(?:-\s*(.*))?$")


def _parse(text):
    """Split a page into (menu_items, plain_lines). menu_items = [(label, target, desc)]."""
    items, lines = [], []
    for line in text.splitlines():
        m = LINK.match(line)
        if m:
            items.append((m.group(1), m.group(2), m.group(3) or ""))
        else:
            lines.append(line)
    return items, lines


class Nav:
    """Fetching and history, shared by both renderers."""

    def __init__(self, home):
        self.home = home
        self.store = home.store()
        self.history = []  # list of (sid, path, addr)
        self.on_fetch = None  # optional callback(sid) fired just before a network fetch (for a loading display)

    def text(self, sid, path, addr):
        """Read a page, fetching it if missing. Returns (text, error)."""
        body = self.store.info(sid)
        if not body or path not in (body or {}).get("files", {}) or self.store.missing(body):
            from . import net
            if self.on_fetch:
                self.on_fetch(sid)
            status, body = net.fetch(self.home, sid, wait=15, hint=addr)
            if status != "ok" and not self.store.info(sid):
                return None, "not found on the network (is a peer connected?)"
        body = self.store.info(sid)
        if not body or path not in body["files"]:
            path = "index.md" if body and "index.md" in body["files"] else (sorted(body["files"])[0] if body else path)
        try:
            return self.store.read(sid, path).decode("utf-8", "replace"), None
        except Exception as e:
            return None, str(e)

    def goto(self, ref):
        """Resolve something a person typed (petname, site id, SITE@NODE) to a history entry.
        Returns (entry, None) or (None, error message)."""
        from .cli import _split_ref, _expand
        ref = ref.strip()
        if not ref:
            return None, "type a site id, a name, or SITE@NODEADDRESS"
        site, addr = _split_ref(_expand(self.home, ref))
        sid = self.store.resolve(site)
        if not sid and len(site) == 32 and all(c in "0123456789abcdef" for c in site.lower()):
            sid = site.lower()
        if not sid:
            return None, "unknown site %r" % ref
        return (sid, "index.md", addr or None), None

    def follow(self, sid, target):
        """A target is another page in this site, or SITE/petname[@ADDR] for a different site."""
        from .cli import _expand
        expanded = _expand(self.home, target)
        t_sid, _, addr = expanded.partition("@")
        if len(t_sid) == 32 and all(c in "0123456789abcdef" for c in t_sid.lower()):
            return (t_sid, "index.md", addr or None)
        return (sid, target, None)

    def run(self, sid, addr, render_page):
        """render_page(sid, path, text, err) -> 'back' | 'quit' | (sid, path, addr) tuple."""
        self.history.append((sid, "index.md", addr))
        while self.history:
            sid, path, addr = self.history[-1]
            text, err = self.text(sid, path, addr)
            action = render_page(sid, path, text, err)
            if action == "back":
                self.history.pop()
            elif action == "quit":
                return
            elif isinstance(action, tuple):
                self.history.append(action)


# ---- curses renderer: full-screen, arrow keys ----

class CursesBrowser:
    def __init__(self, nav, scr):
        self.nav, self.scr = nav, scr

    def run(self, sid, addr):
        self.nav.run(sid, addr, self._page)

    def _page(self, sid, path, text, err):
        scr = self.scr
        items, lines = ([], ["(%s)" % err]) if err else _parse(text)
        sel = 0
        while True:
            curses.curs_set(0)
            try:
                if curses.has_colors():
                    curses.start_color()
                    curses.use_default_colors()
                    curses.init_pair(1, curses.COLOR_WHITE, -1)
                    scr.bkgd(" ", curses.color_pair(1))
            except curses.error:
                pass
            scr.erase()
            h, w = scr.getmaxyx()
            title = " ALTERNET BBS "
            scr.border()
            scr.addstr(0, max(1, (w - len(title)) // 2), title[: w - 2])
            scr.addstr(1, 2, ("%s / %s" % (sid[:12], path))[: w - 4])
            row = 3
            for ln in lines:
                for wrapped in (textwrap.wrap(ln, w - 4) or [""]):
                    if row >= h - 2 - (len(items) and 2):
                        break
                    scr.addstr(row, 2, wrapped[: w - 4])
                    row += 1
            if items:
                row += 1
                for i, (label, target, desc) in enumerate(items):
                    mark = "> " if i == sel else "  "
                    line = "%s%d. %-20s %s" % (mark, i + 1, label, desc)
                    attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
                    if row < h - 2:
                        scr.addstr(row, 2, line[: w - 4], attr)
                        row += 1
            foot = "[up/down] move  [enter] open  [g] go to address  [b] back  [q] quit"
            scr.addstr(h - 1, 2, foot[: w - 4])
            scr.refresh()
            k = scr.getch()
            if k == ord("q"):
                return "quit"
            if k in (ord("b"), curses.KEY_BACKSPACE, 127, 8):
                return "back"
            if k in (ord("g"), ord("/")):
                scr.addstr(h - 2, 2, "go to: "[: w - 4])
                curses.echo(); curses.curs_set(1)
                try:
                    typed = scr.getstr(h - 2, 9, 120).decode("utf-8", "ignore")
                finally:
                    curses.noecho(); curses.curs_set(0)
                entry, msg = self.nav.goto(typed)
                if entry:
                    return entry
                continue
            if items:
                if k in (curses.KEY_DOWN, ord("j")):
                    sel = (sel + 1) % len(items)
                elif k in (curses.KEY_UP, ord("k")):
                    sel = (sel - 1) % len(items)
                elif ord("1") <= k <= ord("9") and k - ord("1") < len(items):
                    sel = k - ord("1")
                    return self.nav.follow(sid, items[sel][1])
                elif k in (curses.KEY_ENTER, 10, 13):
                    return self.nav.follow(sid, items[sel][1])


# ---- raw-ANSI renderer: no curses needed, just termios raw mode + plain ANSI escapes. This is what makes
# a-Shell on iOS feel live (instant arrow keys, highlighted selection) despite having no `_curses` module:
# `termios`/`tty` only need raw single-byte terminal I/O, a much lower bar than the full curses C extension.

CLEAR = "\033[2J\033[H"
BOLD = "\033[1m"
DIM = "\033[2m"
REV = "\033[7m"
RESET = "\033[0m"


class RawAnsiBrowser:
    def __init__(self, nav):
        self.nav = nav

    def run(self, sid, addr):
        fd = sys.stdin.fileno()
        old = self._cooked = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            self.nav.run(sid, addr, self._page)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def _prompt_address(self):
        """Leave raw mode briefly to read one line the normal way, then return to raw mode."""
        fd = sys.stdin.fileno()
        raw = termios.tcgetattr(fd)
        termios.tcsetattr(fd, termios.TCSADRAIN, self._cooked)
        try:
            sys.stdout.write(CLEAR + "Go to (site id, name, or SITE@NODEADDRESS; empty = cancel): ")
            sys.stdout.flush()
            return input().strip()
        except EOFError:
            return ""
        finally:
            tty.setraw(fd)
            termios.tcsetattr(fd, termios.TCSADRAIN, raw)

    def _getkey(self, timeout=None):
        import os, select
        if timeout is not None:
            r, _, _ = select.select([sys.stdin], [], [], timeout)
            if not r:
                return "tick"
        ch = os.read(sys.stdin.fileno(), 1)
        if ch == b"\x1b":
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                ch2 = os.read(sys.stdin.fileno(), 1)
                if ch2 == b"[":
                    ch3 = os.read(sys.stdin.fileno(), 1)
                    if ch3 == b"<":                       # SGR mouse report: ESC [ < b ; x ; y (M|m)
                        buf = b""
                        while not buf.endswith((b"M", b"m")) and len(buf) < 20:
                            buf += os.read(sys.stdin.fileno(), 1)
                        try:
                            b_, x_, y_ = buf[:-1].decode().split(";")
                            if buf.endswith(b"M") and int(b_) == 0:
                                return ("click", int(x_), int(y_))
                        except ValueError:
                            pass
                        return None
                    return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(ch3.decode("latin1"), None)
            return "esc"
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch in (b"\x7f", b"\x08"):
            return "backspace"
        if ch in (b"\x03",):  # Ctrl-C
            return "quit"
        try:
            return ch.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _page(self, sid, path, text, err):
        items, lines = ([], ["(%s)" % err]) if err else _parse(text)
        sel = 0
        while True:
            w, h = shutil.get_terminal_size(fallback=(78, 24))
            w = max(40, min(w, 100))
            out = [CLEAR]
            title = " ALTERNET BBS "
            out.append(BOLD + title.center(w, "=") + RESET)
            out.append(DIM + ("%s / %s" % (sid[:12], path)) + RESET)
            out.append("-" * w)
            shown = 0
            for ln in lines:
                for wrapped in (textwrap.wrap(ln, w) or [""]):
                    if shown >= h - 6 - (len(items) and len(items) + 1):
                        break
                    out.append(wrapped)
                    shown += 1
            if items:
                out.append("-" * w)
                for i, (label, target, desc) in enumerate(items):
                    line = "  %d. %-20s %s" % (i + 1, label, desc)
                    out.append((REV + line + RESET) if i == sel else line)
            out.append("-" * w)
            out.append("[up/down or j/k] move  [enter] open  [g] go to address  [b] back  [q] quit")
            sys.stdout.write("\r\n".join(out) + "\r\n")
            sys.stdout.flush()
            k = self._getkey()
            if k in ("q", "quit"):
                return "quit"
            if k in ("b", "backspace"):
                return "back"
            if k in ("g", "/"):
                entry, msg = self.nav.goto(self._prompt_address())
                if entry:
                    return entry
                continue
            if items:
                if k in ("down", "j"):
                    sel = (sel + 1) % len(items)
                elif k in ("up", "k"):
                    sel = (sel - 1) % len(items)
                elif k and k.isdigit() and 1 <= int(k) <= len(items):
                    sel = int(k) - 1
                    return self.nav.follow(sid, items[sel][1])
                elif k == "enter":
                    return self.nav.follow(sid, items[sel][1])


# ---- plain renderer: print()/input(), works anywhere, classic BBS feel ----

W = 70


def _ansi_ok():
    """Best-effort: only disable styling for something that clearly can't render ANSI (no tty, or a
    dumb terminal). Not perfect, but a-Shell/SSH/Terminal.app/iTerm all pass this."""
    import os as _os
    import sys as _sys
    return _sys.stdout.isatty() and _os.environ.get("TERM", "") not in ("", "dumb")


class PlainBrowser:
    """No curses, but still a boxed, cleared-screen page per step using plain ANSI escapes (which a-Shell's
    terminal renders fine even though it has no curses module). Navigation is still type-a-number-then-Enter,
    since there is no portable way to read single keystrokes without curses/termios here."""

    def __init__(self, nav):
        self.nav = nav
        self.ansi = _ansi_ok()

    def run(self, sid, addr):
        self.nav.run(sid, addr, self._page)

    def _rule(self, ch="-"):
        return ch * W

    def _page(self, sid, path, text, err):
        items, lines = ([], ["(%s)" % err]) if err else _parse(text)
        out = []
        if self.ansi:
            out.append(CLEAR)
            title = " ALTERNET BBS "
            out.append(BOLD + title.center(W, "=") + RESET)
        else:
            out.append(self._rule("="))
            out.append("ALTERNET BBS")
            out.append(self._rule("="))
        out.append((DIM if self.ansi else "") + ("%s / %s" % (sid[:12], path)) + (RESET if self.ansi else ""))
        out.append(self._rule())
        for ln in lines:
            for wrapped in (textwrap.wrap(ln, W) or [""]):
                out.append(wrapped)
        if items:
            out.append(self._rule())
            for i, (label, target, desc) in enumerate(items):
                num = (BOLD + str(i + 1) + RESET) if self.ansi else str(i + 1)
                out.append("  %s. %-20s %s" % (num, label, desc))
        out.append(self._rule())
        print("\n".join(out))
        while True:
            choice = input("[number]=open  [b]=back  [q]=quit  or type an address > ").strip().lower()
            if choice == "q":
                return "quit"
            if choice == "b":
                return "back"
            if choice.isdigit() and items and 1 <= int(choice) <= len(items):
                return self.nav.follow(sid, items[int(choice) - 1][1])
            if choice and choice not in ("q", "b") and not choice.isdigit():
                entry, msg = self.nav.goto(choice)
                if entry:
                    return entry
                print(msg)
                continue
            print("not a valid choice")


# ---- fancy renderer: truecolor "terminal game" screen. Same navigation, plus an address bar and a status
# line. Needs raw tty + a truecolor terminal (COLORTERM=truecolor), otherwise run() falls back automatically.

def _rgb(r, g, b, bg=False):
    return "\033[%d;2;%d;%d;%dm" % (48 if bg else 38, r, g, b)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


CYAN, MAGENTA, GOLD = (60, 220, 255), (220, 80, 255), (255, 200, 80)


def _gradient(text, c1=CYAN, c2=MAGENTA):
    n = max(len(text) - 1, 1)
    return "".join(_rgb(*_lerp(c1, c2, i / n)) + ch for i, ch in enumerate(text)) + RESET


def _stars(w, tick, row):
    out = []
    for x in range(w):
        v = (x * 7919 + row * 104729 + (tick // 2) * 1299709) % 41
        out.append(DIM + _rgb(150, 170, 255) + "·" + RESET if v == 0 else
                   _rgb(255, 255, 255) + "✦" + RESET if v == 1 and tick % 2 else " ")
    return "".join(out)


def _vlen(s):
    return len(re.sub(r"\033\[[0-9;?]*[A-Za-z]", "", s))


def fancy_frame(sid, path, items, lines, sel, edit, status, tick, w, h):
    """Build one screen as a list of strings (pure function, so it can be tested without a terminal)."""
    out = [_stars(w, tick, 0),
           " " * ((w - 21) // 2) + BOLD + _gradient("◆  A L T E R N E T  ◆") + RESET,
           _stars(w, tick, 1)]
    label = "address" if edit is None else "address (Enter=go, down=menu)"
    inner = w - 4
    out.append(_rgb(*CYAN) + "╭─ " + label + " " + "─" * max(0, w - 5 - len(label)) + "╮" + RESET)
    if edit is None:
        loc = "%s / %s" % (sid[:12], path)
        hint = "   press g to type an address"
        body = DIM + (loc + hint)[:inner] + RESET
    else:
        body = _rgb(*GOLD) + edit[-(inner - 1):] + RESET + REV + " " + RESET
        if not edit:
            body += DIM + " type a site id or name, Enter to go  |  down-arrow for the menu" + RESET
            body = body[: len(body)]
    pad = max(0, inner - _vlen(body))
    out.append(_rgb(*CYAN) + "│ " + RESET + body + " " * pad + _rgb(*CYAN) + " │" + RESET)
    out.append(_rgb(*CYAN) + "╰" + "─" * (w - 2) + "╯" + RESET)
    reserved = 2                       # status line + key hint always stay on screen
    free = max(0, h - len(out) - reserved)
    n_items = min(len(items), max(1, free - 1)) if items else 0
    room = free - (n_items + 1 if items else 0)
    shown = 0
    for ln in lines:
        for wrapped in (textwrap.wrap(ln, w - 2) or [""]):
            if shown >= room:
                break
            if wrapped.lstrip().startswith("#"):
                wrapped = BOLD + _gradient(wrapped.lstrip("# ").strip(), GOLD, CYAN)
            out.append(" " + wrapped)
            shown += 1
    if items:
        out.append("")
        first = max(0, min(sel - n_items + 1, len(items) - n_items)) if sel >= n_items else 0
        for i in range(first, first + n_items):
            name, target, desc = items[i]
            text = " %s %d  %-18s %s" % ("▸" if i == sel else " ", i + 1, name, desc)
            text = text[: w - 1].ljust(w - 1)
            out.append((_rgb(25, 45, 95, bg=True) + _rgb(255, 255, 255) + BOLD + text + RESET) if i == sel
                       else (DIM + text + RESET))
    while len(out) < h - 2:
        out.append("")
    out.append(_rgb(120, 255, 160) + " ● " + RESET + DIM + status[: w - 4] + RESET)
    out.append(DIM + " [arrows/jk] move  [enter] open  [g] address  [w] 3D walk  [b] back  [q] quit"[:w] + RESET)
    return out[:h]


class FancyBrowser(RawAnsiBrowser):
    def run(self, sid, addr):
        fd = sys.stdin.fileno()
        self._cooked = termios.tcgetattr(fd)
        self.sites = len(self.nav.store.sites())
        conn = self.nav.home.settings().get("connect") or []
        self.relay = conn[0] if conn else "no relay (local only)"
        self.nav.on_fetch = self._loading
        self._first = True
        sys.stdout.write("\033[?1049h\033[?25l" + CLEAR)
        try:
            tty.setraw(fd)
            self.nav.run(sid, addr, self._page)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, self._cooked)
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()

    def _size(self):
        w, h = shutil.get_terminal_size(fallback=(80, 24))
        return max(50, min(w, 110)), max(14, h)

    tick_seconds = 0.5

    def _paint(self, sid, path, items, lines, sel, edit, status, tick, w, h):
        self._draw(fancy_frame(sid, path, items, lines, sel, edit, status, tick, w, h))

    def _hit(self, x, y):
        return None

    def _clear_images(self):
        return ""

    def _draw(self, frame):
        sys.stdout.write("\033[H" + "\r\n".join(ln + "\033[K" for ln in frame))
        sys.stdout.flush()

    def _loading(self, sid):
        w, h = self._size()
        msg = "fetching %s... and verifying every signature and block" % sid[:12]
        self._draw(fancy_frame(sid, "...", [], ["", msg], 0, None, "joining the network via " + self.relay, 0, w, h))

    def _status(self):
        return "online via %s | %d site(s) stored | every page is signature-checked" % (self.relay, self.sites)

    def _page(self, sid, path, text, err):
        items, lines = ([], ["(%s)" % err]) if err else _parse(text)
        sel, tick, flash = 0, 0, None
        edit = "" if self._first else None   # the very first screen of a session: address bar has focus
        self._first = False
        while True:
            w, h = self._size()
            self._paint(sid, path, items, lines, sel, edit, flash or self._status(), tick, w, h)
            k = self._getkey(timeout=self.tick_seconds)
            if k == "tick":
                tick += 1
                continue
            flash = None
            if isinstance(k, tuple):                       # a mouse click -> the equivalent key press
                act = self._hit(k[1], k[2])
                if act is None:
                    continue
                if act[0] == "item":
                    edit, sel, k = None, act[1], "enter"
                else:
                    edit, k = (None, {"back": "b", "world": "w"}[act[0]]) if act[0] != "addr" else ("", "g")
                    if act[0] == "addr":
                        continue
            if edit is not None:
                if k in ("esc", "quit", "down"):
                    edit = None
                elif k == "enter":
                    if not edit:
                        edit = None
                        continue
                    entry, flash = self.nav.goto(edit)
                    edit = None
                    if entry:
                        return entry
                elif k == "backspace":
                    edit = edit[:-1]
                elif k == "\x15":
                    edit = ""
                elif k and len(k) == 1 and k.isprintable():
                    edit += k
                continue
            if k in ("q", "quit"):
                return "quit"
            if k in ("b", "backspace"):
                return "back"
            if k == "w":
                from . import world
                ref = world.play(world.World(world.doors_for(self.nav.home) or [("this site", sid)]),
                                 self._getkey, lambda t: (sys.stdout.write(t), sys.stdout.flush()), self._size)
                sys.stdout.write(self._clear_images() + CLEAR)
                if ref:
                    entry, flash = self.nav.goto(ref)
                    if entry:
                        return entry
                continue
            if k in ("g", "/") or (k == "up" and sel == 0):
                edit = ""
            elif items:
                if k in ("down", "j"):
                    sel = (sel + 1) % len(items)
                elif k in ("up", "k"):
                    sel = (sel - 1) % len(items)
                elif k and k.isdigit() and 1 <= int(k) <= len(items):
                    return self.nav.follow(sid, items[int(k) - 1][1])
                elif k == "enter":
                    return self.nav.follow(sid, items[sel][1])


# ---- pixel renderer: draws the whole interface into a real pixel canvas (own font, gradients, buttons) and
# shows it with an inline-image protocol, so it is not limited to the character grid. Falls back (in run())
# to the character renderers when the terminal cannot display images.

BG1, BG2 = (8, 10, 30), (34, 12, 52)
PANEL, BAR, ACCENT, TEXT, DIMT = (12, 14, 36), (14, 18, 46), (60, 220, 255), (232, 236, 250), (130, 140, 175)
SELBG, ITEMBG, GOLDC = (30, 62, 150), (22, 26, 60), (255, 200, 80)
CELL_W, CELL_H = 8, 16


def pixel_frame(sid, path, items, lines, sel, edit, status, W, H):
    """Draw one screen. Returns (Canvas, hits) where hits = [(x0, y0, x1, y1, action)] for mouse clicks."""
    from .canvas import Canvas, lerp
    c, hits, m = Canvas(W, H), [], 16
    c.vgradient(0, 0, W, H, BG1, BG2)
    # top bar
    c.rect(0, 0, W, 34, BAR); c.rect(0, 34, W, 2, ACCENT)
    c.text(14, 10, "ALTERNET", ACCENT, 2, gradient_to=(220, 80, 255))
    for label, act, bx in (("BACK", "back", W - 188), ("3D", "world", W - 90)):
        bw = c.text_width(label) + 20
        c.rect(bx, 5, bw, 24, SELBG); c.border(bx, 5, bw, 24, ACCENT)
        c.text(bx + 10, 9, label, TEXT)
        hits.append((bx, 5, bx + bw, 29, (act,)))
    # address field
    fx, fy, fw = m, 48, W - 2 * m
    c.rect(fx, fy, fw, 34, (8, 10, 26))
    c.border(fx, fy, fw, 34, GOLDC if edit is not None else (70, 95, 150), 2)
    maxc = (fw - 24) // 12
    if edit is None:
        c.text(fx + 12, fy + 9, ("%s / %s" % (sid[:12], path))[:maxc], TEXT)
        hint = "  click or press g to type an address"
        room = maxc - len(sid[:12]) - len(path) - 3
        if room > 10:
            c.text(fx + 12 + c.text_width("%s / %s" % (sid[:12], path)), fy + 9, hint[:room], DIMT)
    else:
        shown = edit[-(maxc - 1):]
        x = c.text(fx + 12, fy + 9, shown, GOLDC)
        c.rect(x + 1, fy + 8, 10, 18, GOLDC)
        if not edit:
            c.text(x + 18, fy + 9, "type a site id or name, Enter to go, Down for the menu"[: maxc - 3], DIMT)
    hits.append((fx, fy, fx + fw, fy + 34, ("addr",)))
    # page window
    wx, wy, ww = m, 96, W - 2 * m
    wh = H - wy - 44
    c.rect(wx, wy, ww, wh, PANEL); c.border(wx, wy, ww, wh, (70, 95, 150), 2)
    c.vgradient(wx + 2, wy + 2, ww - 4, 24, (40, 70, 170), (28, 24, 90))
    c.text(wx + 12, wy + 6, ("%s" % path)[: (ww - 24) // 12], TEXT)
    ix, iw, ih = wx + 14, ww - 28, 30
    n_items = min(len(items), max(1, (wh - 120) // (ih + 6))) if items else 0
    menu_h = n_items * (ih + 6)
    ty, tmax = wy + 36, wy + wh - menu_h - 12
    per_line = max(10, (ww - 28) // 12)
    for ln in lines:
        for wrapped in (textwrap.wrap(ln, per_line) or [""]):
            if ty + 18 > tmax:
                break
            head = wrapped.lstrip().startswith("#")
            c.text(ix, ty, wrapped.lstrip("# ").strip() if head else wrapped, GOLDC if head else TEXT)
            ty += 20 if head else 18
    first = max(0, min(sel - n_items + 1, len(items) - n_items)) if items and sel >= n_items else 0
    iy = wy + wh - menu_h - 6
    for i in range(first, first + n_items):
        name, target, desc = items[i]
        on = i == sel
        c.rect(ix, iy, iw, ih, SELBG if on else ITEMBG)
        c.border(ix, iy, iw, ih, ACCENT if on else (46, 54, 110), 1)
        if on:
            c.rect(ix, iy, 6, ih, GOLDC)
        c.text(ix + 16, iy + 7, "%d" % (i + 1), GOLDC if on else DIMT)
        x = c.text(ix + 46, iy + 7, name[:24], TEXT)
        c.text(ix + 46 + 24 * 12 + 12, iy + 7, desc[: max(0, (iw - 46 - 24 * 12 - 24) // 12)], (190, 200, 230) if on else DIMT)
        hits.append((ix, iy, ix + iw, iy + ih, ("item", i)))
        iy += ih + 6
    # status bar
    c.rect(0, H - 34, W, 34, BAR); c.rect(0, H - 36, W, 2, ACCENT)
    c.rect(14, H - 22, 10, 10, (120, 255, 160))
    c.text(34, H - 25, status[: (W - 48) // 12], DIMT)
    return c, hits


class PixelBrowser(FancyBrowser):
    tick_seconds = None

    def __init__(self, nav, protocol):
        super().__init__(nav)
        self.protocol = protocol
        self._hits, self._dims = [], (1, 1, 1, 1)

    def _size(self):
        w, h = shutil.get_terminal_size(fallback=(100, 30))
        return max(60, min(w, 200)), max(20, min(h, 60))

    def run(self, sid, addr):
        sys.stdout.write("\033[?1000h\033[?1006h")        # report mouse clicks
        try:
            super().run(sid, addr)
        finally:
            sys.stdout.write("\033[?1006l\033[?1000l" + self._clear_images())
            sys.stdout.flush()

    def _clear_images(self):
        from .canvas import KITTY_CLEAR
        return KITTY_CLEAR if self.protocol == "kitty" else ""

    def _paint(self, sid, path, items, lines, sel, edit, status, tick, cols, rows):
        from .canvas import encode_image
        W, H = cols * CELL_W, (rows - 1) * CELL_H
        canvas, self._hits = pixel_frame(sid, path, items, lines, sel, edit, status, W, H)
        self._dims = (W, H, cols, rows - 1)
        sys.stdout.write("\033[H" + encode_image(canvas.png(), self.protocol, cols, rows - 1))
        sys.stdout.flush()

    def _loading(self, sid):
        cols, rows = self._size()
        self._paint(sid, "...", [], ["", "fetching %s... and verifying every signature and block" % sid[:12]],
                    0, None, "joining the network via " + self.relay, 0, cols, rows)

    def _hit(self, cx, cy):
        W, H, cols, rows = self._dims
        px, py = (cx - 0.5) * W / cols, (cy - 0.5) * H / rows
        for x0, y0, x1, y1, act in self._hits:
            if x0 <= px < x1 and y0 <= py < y1:
                return act
        return None


def run(home, ref, force_plain=False, mode=None):
    """mode: None picks the best available (curses > raw ANSI > plain line-input); or force one of
    'curses', 'raw', 'plain' explicitly (used by --plain / --raw, and by tests)."""
    from .cli import _split_ref, _expand, die
    site, addr = _split_ref(_expand(home, ref))
    sid = home.store().resolve(site)
    if not sid and len(site) == 32:
        sid = site
    if not sid:
        die("unknown site %r" % site)
    nav = Nav(home)
    if force_plain:
        mode = "plain"
    if mode is None:
        import os as _os
        truecolor = _os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        from .canvas import detect_protocol
        if HAVE_RAWTTY and sys.stdin.isatty() and sys.stdout.isatty() and detect_protocol():
            mode = "pixel"
        elif HAVE_RAWTTY and truecolor and sys.stdin.isatty() and sys.stdout.isatty():
            mode = "fancy"
    if mode is None:
        mode = "curses" if HAVE_CURSES else ("raw" if (HAVE_RAWTTY and sys.stdin.isatty()) else "plain")
    if mode == "pixel" and HAVE_RAWTTY:
        from .canvas import detect_protocol
        proto = detect_protocol() or detect_protocol("iterm")
        PixelBrowser(nav, proto).run(sid, addr)
    elif mode == "fancy" and HAVE_RAWTTY:
        FancyBrowser(nav).run(sid, addr)
    elif mode == "curses" and HAVE_CURSES:
        curses.wrapper(lambda scr: CursesBrowser(nav, scr).run(sid, addr))
    elif mode == "raw" and HAVE_RAWTTY:
        RawAnsiBrowser(nav).run(sid, addr)
    else:
        PlainBrowser(nav).run(sid, addr)
