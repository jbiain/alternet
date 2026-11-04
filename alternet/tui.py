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

    def text(self, sid, path, addr):
        """Read a page, fetching it if missing. Returns (text, error)."""
        body = self.store.info(sid)
        if not body or path not in (body or {}).get("files", {}) or self.store.missing(body):
            from . import net
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
            foot = "[up/down] move  [enter] open  [b] back  [q] quit"
            scr.addstr(h - 1, 2, foot[: w - 4])
            scr.refresh()
            k = scr.getch()
            if k == ord("q"):
                return "quit"
            if k in (ord("b"), curses.KEY_BACKSPACE, 127, 8):
                return "back"
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
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            self.nav.run(sid, addr, self._page)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def _getkey(self):
        import os, select
        ch = os.read(sys.stdin.fileno(), 1)
        if ch == b"\x1b":
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                ch2 = os.read(sys.stdin.fileno(), 1)
                if ch2 == b"[":
                    ch3 = os.read(sys.stdin.fileno(), 1)
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
            out.append("[up/down or j/k] move  [enter] open  [b] back  [q] quit")
            sys.stdout.write("\r\n".join(out) + "\r\n")
            sys.stdout.flush()
            k = self._getkey()
            if k in ("q", "quit"):
                return "quit"
            if k in ("b", "backspace"):
                return "back"
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
            choice = input("[number]=open  [b]=back  [q]=quit > ").strip().lower()
            if choice == "q":
                return "quit"
            if choice == "b":
                return "back"
            if choice.isdigit() and items and 1 <= int(choice) <= len(items):
                return self.nav.follow(sid, items[int(choice) - 1][1])
            print("not a valid choice")


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
        mode = "curses" if HAVE_CURSES else ("raw" if (HAVE_RAWTTY and sys.stdin.isatty()) else "plain")
    if mode == "curses" and HAVE_CURSES:
        curses.wrapper(lambda scr: CursesBrowser(nav, scr).run(sid, addr))
    elif mode == "raw" and HAVE_RAWTTY:
        RawAnsiBrowser(nav).run(sid, addr)
    else:
        PlainBrowser(nav).run(sid, addr)
