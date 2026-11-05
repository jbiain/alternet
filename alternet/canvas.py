"""A tiny software pixel canvas for drawing a real (not character-grid) interface: rectangles, gradients,
borders and bitmap-font text, plus ways to show the result in a terminal that can display images (the
Kitty graphics protocol and the iTerm2 inline-image protocol, also understood by WezTerm, Ghostty and others).
Standard library only. A colour is an (r, g, b) tuple."""
import base64, os, struct, zlib

# 5x7 font, 7 rows per glyph, 5 bits per row (bit 4 = leftmost). ASCII 32..126.
_FONT_ROWS = """
00 00 00 00 00 00 00|04 04 04 04 04 00 04|0A 0A 0A 00 00 00 00|0A 0A 1F 0A 1F 0A 0A|04 0F 14 0E 05 1E 04
18 19 02 04 08 13 03|0C 12 14 08 15 12 0D|0C 04 08 00 00 00 00|02 04 08 08 08 04 02|08 04 02 02 02 04 08
00 04 15 0E 15 04 00|00 04 04 1F 04 04 00|00 00 00 00 0C 04 08|00 00 00 1F 00 00 00|00 00 00 00 00 0C 0C
00 01 02 04 08 10 00|0E 11 13 15 19 11 0E|04 0C 04 04 04 04 0E|0E 11 01 02 04 08 1F|1F 02 04 02 01 11 0E
02 06 0A 12 1F 02 02|1F 10 1E 01 01 11 0E|06 08 10 1E 11 11 0E|1F 01 02 04 08 08 08|0E 11 11 0E 11 11 0E
0E 11 11 0F 01 02 0C|00 0C 0C 00 0C 0C 00|00 0C 0C 00 0C 04 08|02 04 08 10 08 04 02|00 00 1F 00 1F 00 00
08 04 02 01 02 04 08|0E 11 01 02 04 00 04|0E 11 01 0D 15 15 0E|0E 11 11 1F 11 11 11|1E 11 11 1E 11 11 1E
0E 11 10 10 10 11 0E|1C 12 11 11 11 12 1C|1F 10 10 1E 10 10 1F|1F 10 10 1E 10 10 10|0E 11 10 17 11 11 0F
11 11 11 1F 11 11 11|0E 04 04 04 04 04 0E|07 02 02 02 02 12 0C|11 12 14 18 14 12 11|10 10 10 10 10 10 1F
11 1B 15 15 11 11 11|11 11 19 15 13 11 11|0E 11 11 11 11 11 0E|1E 11 11 1E 10 10 10|0E 11 11 11 15 12 0D
1E 11 11 1E 14 12 11|0F 10 10 0E 01 01 1E|1F 04 04 04 04 04 04|11 11 11 11 11 11 0E|11 11 11 11 11 0A 04
11 11 11 15 15 15 0A|11 11 0A 04 0A 11 11|11 11 11 0A 04 04 04|1F 01 02 04 08 10 1F|0E 08 08 08 08 08 0E
00 10 08 04 02 01 00|0E 02 02 02 02 02 0E|04 0A 11 00 00 00 00|00 00 00 00 00 00 1F|08 04 02 00 00 00 00
00 00 0E 01 0F 11 0F|10 10 16 19 11 11 1E|00 00 0E 10 10 11 0E|01 01 0D 13 11 11 0F|00 00 0E 11 1F 10 0E
06 09 08 1C 08 08 08|00 0F 11 11 0F 01 0E|10 10 16 19 11 11 11|04 00 0C 04 04 04 0E|02 00 06 02 02 12 0C
10 10 12 14 18 14 12|0C 04 04 04 04 04 0E|00 00 1A 15 15 11 11|00 00 16 19 11 11 11|00 00 0E 11 11 11 0E
00 00 1E 11 1E 10 10|00 00 0D 13 0F 01 01|00 00 16 19 10 10 10|00 00 0F 10 0E 01 1E|08 08 1C 08 08 09 06
00 00 11 11 11 13 0D|00 00 11 11 11 0A 04|00 00 11 11 15 15 0A|00 00 11 0A 04 0A 11|00 00 11 11 0F 01 0E
00 00 1F 02 04 08 1F|02 04 04 08 04 04 02|04 04 04 04 04 04 04|08 04 04 02 04 04 08|00 00 08 15 02 00 00
"""
GLYPHS = [[int(b, 16) for b in g.split()] for g in _FONT_ROWS.replace("\n", "|").split("|") if g.strip()]
assert len(GLYPHS) == 95, len(GLYPHS)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    def __init__(self, w, h, color=(0, 0, 0)):
        self.w, self.h = w, h
        self.buf = bytearray(bytes(color) * (w * h))

    def rect(self, x, y, w, h, color):
        x0, x1 = max(0, x), min(self.w, x + w)
        if x1 <= x0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(max(0, y), min(self.h, y + h)):
            o = (yy * self.w + x0) * 3
            self.buf[o:o + len(row)] = row

    def vgradient(self, x, y, w, h, c1, c2):
        for i in range(h):
            self.rect(x, y + i, w, 1, lerp(c1, c2, i / max(h - 1, 1)))

    def border(self, x, y, w, h, color, t=1):
        self.rect(x, y, w, t, color); self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color); self.rect(x + w - t, y, t, h, color)

    def text_width(self, s, scale=2):
        return len(s) * 6 * scale

    def text(self, x, y, s, color, scale=2, gradient_to=None):
        """Draw text with the bitmap font; returns the x just after it. Characters outside ASCII show as '?'."""
        n = max(len(s) - 1, 1)
        for i, ch in enumerate(s):
            c = lerp(color, gradient_to, i / n) if gradient_to else color
            code = ord(ch)
            g = GLYPHS[code - 32] if 32 <= code <= 126 else GLYPHS[ord("?") - 32]
            for gy, bits in enumerate(g):
                gy_draw = gy + (1 if ch == "g" else 0)       # let g hang below the baseline instead of reading as 9
                gx = 0
                while gx < 5:
                    if bits & (0x10 >> gx):
                        run = 1
                        while gx + run < 5 and bits & (0x10 >> (gx + run)):
                            run += 1
                        self.rect(x + gx * scale, y + gy_draw * scale, run * scale, scale, c)
                        gx += run
                    else:
                        gx += 1
            x += 6 * scale
        return x

    def png(self):
        stride = self.w * 3
        raw = b"".join(b"\x00" + bytes(self.buf[y * stride:(y + 1) * stride]) for y in range(self.h))

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def detect_protocol(force=None):
    """Which inline-image protocol this terminal speaks: 'kitty', 'iterm', or None. `force` (or the
    ALTERNET_PIXEL env var) overrides detection; used for terminals we cannot reliably detect."""
    v = (force or os.environ.get("ALTERNET_PIXEL", "")).lower()
    if v in ("kitty", "iterm"):
        return v
    if v in ("none", "off"):
        return None
    env = os.environ
    if env.get("KITTY_WINDOW_ID") or env.get("TERM", "").startswith("xterm-kitty") or env.get("TERM_PROGRAM") == "ghostty":
        return "kitty"
    if env.get("TERM_PROGRAM") in ("iTerm.app", "WezTerm"):
        return "iterm"
    return None


def encode_image(png, protocol, cols, rows):
    """Escape sequence that draws `png` at the cursor, stretched over cols x rows character cells."""
    b64 = base64.b64encode(png).decode()
    if protocol == "kitty":
        parts, first = [b64[i:i + 4096] for i in range(0, len(b64), 4096)], True
        out = []
        for i, p in enumerate(parts):
            more = 1 if i < len(parts) - 1 else 0
            head = "a=T,f=100,i=1,c=%d,r=%d,C=1,q=2,m=%d" % (cols, rows, more) if first else "m=%d" % more
            out.append("\033_G%s;%s\033\\" % (head, p))
            first = False
        return "".join(out)
    return "\033]1337;File=inline=1;width=%d;height=%d;preserveAspectRatio=0;size=%d:%s\a" % (cols, rows, len(png), b64)


KITTY_CLEAR = "\033_Ga=d,q=2\033\\"
