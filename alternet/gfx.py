"""Terminal graphics with nothing but the standard library: a small PNG decoder and a truecolor half-block
renderer (each character cell shows two vertically stacked pixels using the upper-half-block glyph, so a
100x40 terminal is a 100x80 pixel screen). A pixel image is a list of rows, each row a list of (r, g, b)."""
import struct, zlib

RESET = "\033[0m"


def decode_png(data):
    """Decode a non-interlaced 8-bit PNG (grey, grey+alpha, RGB, RGBA, or palette) to (w, h, rows)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, plte, ihdr = 8, [], None, None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            plte = chunk
        elif kind == b"IDAT":
            idat.append(chunk)
        elif kind == b"IEND":
            break
    if not ihdr:
        raise ValueError("PNG has no header")
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or interlace != 0 or ctype not in (0, 2, 3, 4, 6):
        raise ValueError("only non-interlaced 8-bit PNGs are supported")
    if w * h > 4_000_000:
        raise ValueError("image too large")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride, rows, prev = w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        base = y * (stride + 1)
        ft, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        if len(line) != stride:
            raise ValueError("truncated PNG data")
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1: line[i] = (line[i] + a) & 255
            elif ft == 2: line[i] = (line[i] + b) & 255
            elif ft == 3: line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif ft != 0:
                raise ValueError("bad PNG filter")
        prev = line
        row = []
        for x in range(w):
            q = x * bpp
            if ctype == 2: px = (line[q], line[q + 1], line[q + 2])
            elif ctype == 6:
                al = line[q + 3]
                px = (line[q] * al // 255, line[q + 1] * al // 255, line[q + 2] * al // 255)
            elif ctype == 0: px = (line[q],) * 3
            elif ctype == 4: px = (line[q] * line[q + 1] // 255,) * 3
            else:
                if plte is None or line[q] * 3 + 2 >= len(plte):
                    raise ValueError("bad PNG palette")
                px = tuple(plte[line[q] * 3:line[q] * 3 + 3])
            row.append(px)
        rows.append(row)
    return w, h, rows


def resize(rows, w, h, new_w, new_h):
    """Nearest-neighbour resize (fast, and fine at terminal resolution)."""
    return [[rows[y * h // new_h][x * w // new_w] for x in range(new_w)] for y in range(new_h)]


def fit(w, h, max_w, max_h_pixels):
    """Largest size with the same aspect that fits the box (small images are scaled up to fill it)."""
    scale = min(max_w / w, max_h_pixels / h)
    return max(1, int(w * scale)), max(1, int(h * scale))


def halfblocks(rows):
    """Render pixel rows to terminal lines. An odd last row is paired with black."""
    lines = []
    for y in range(0, len(rows), 2):
        top = rows[y]
        bot = rows[y + 1] if y + 1 < len(rows) else [(0, 0, 0)] * len(top)
        out, last = [], None
        for t, b in zip(top, bot):
            key = (t, b)
            if key != last:
                out.append("\033[38;2;%d;%d;%d;48;2;%d;%d;%dm" % (t + b))
                last = key
            out.append("▀")
        lines.append("".join(out) + RESET)
    return lines


def render_png(data, max_cols, max_rows):
    """PNG bytes -> terminal lines that fit in max_cols x max_rows character cells."""
    w, h, rows = decode_png(data)
    nw, nh = fit(w, h, max_cols, max_rows * 2)
    return halfblocks(resize(rows, w, h, nw, nh))
