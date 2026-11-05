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
        from .cli import _split_ref, _expand, NameChanged
        ref = ref.strip()
        if not ref:
            return None, "type a site id, a name, or SITE@NODEADDRESS"
        try:
            site, addr = _split_ref(_expand(self.home, ref))
        except NameChanged as e:
            return None, str(e)
        sid = self.store.resolve(site)
        if not sid and len(site) == 32 and all(c in "0123456789abcdef" for c in site.lower()):
            sid = site.lower()
        if not sid:
            return None, "unknown site %r" % ref
        return (sid, "index.md", addr or None), None

    def follow(self, sid, target):
        """A target is another page in this site, or SITE/petname[@ADDR] for a different site."""
        from .cli import _expand, NameChanged
        try:
            expanded = _expand(self.home, target)
        except NameChanged:
            return None
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
        if ln.startswith("\x00"):                      # pre-formatted (images, form fields): do not wrap or restyle
            if shown < room:
                out.append(ln[1:])
                shown += 1
            continue
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
        from . import pagefmt
        bl = pagefmt.blocks(lines)
        fnames = pagefmt.fields(bl)
        values, focus, imgcache = self.nav.home.form_values(sid), None, {}
        sel, tick, flash = 0, 0, None
        edit = "" if self._first else None   # the very first screen of a session: address bar has focus
        self._first = False
        while True:
            w, h = self._size()
            shown = pagefmt.render(bl, values, focus, self.nav.store, sid, w, image_rows=max(4, min(12, h // 3)),
                                   cache=imgcache)
            if fnames and focus is None:
                shown.append("\x00" + DIM + "  [f] edit the fields on this page" + RESET)
            offline = " | stored here: works offline" if self.nav.store.complete(sid) else ""
            self._draw(fancy_frame(sid, path, items, shown, sel, edit, flash or (self._status() + offline), tick, w, h))
            k = self._getkey(timeout=0.5)
            if k == "tick":
                tick += 1
                continue
            flash = None
            if focus is not None:                       # editing a form field
                kind, name = fnames[focus]
                if k in ("esc", "enter", "quit"):
                    focus = None
                    self.nav.home.save_form_values(sid, values)
                elif k in ("\t", "down"):
                    focus = (focus + 1) % len(fnames)
                elif k == "up":
                    focus = (focus - 1) % len(fnames)
                elif kind == "check" and k == " ":
                    values[name] = "" if values.get(name) else "1"
                elif kind == "input" and k == "backspace":
                    values[name] = values.get(name, "")[:-1]
                elif kind == "input" and k and len(k) == 1 and k.isprintable() and len(values.get(name, "")) < 40:
                    values[name] = values.get(name, "") + k
                continue
            if k == "f" and edit is None and fnames:
                focus = 0
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
                sys.stdout.write(CLEAR)
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
        if HAVE_RAWTTY and truecolor and sys.stdin.isatty() and sys.stdout.isatty():
            mode = "fancy"
    if mode is None:
        mode = "curses" if HAVE_CURSES else ("raw" if (HAVE_RAWTTY and sys.stdin.isatty()) else "plain")
    if mode == "fancy" and HAVE_RAWTTY:
        FancyBrowser(nav).run(sid, addr)
    elif mode == "curses" and HAVE_CURSES:
        curses.wrapper(lambda scr: CursesBrowser(nav, scr).run(sid, addr))
    elif mode == "raw" and HAVE_RAWTTY:
        RawAnsiBrowser(nav).run(sid, addr)
    else:
        PlainBrowser(nav).run(sid, addr)
