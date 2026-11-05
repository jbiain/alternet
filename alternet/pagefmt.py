"""Page extras that need no code from the publisher: images and simple forms.

A page is still Markdown. These lines get special treatment in the fancy browser:

    ![A short description](picture.png)           an image stored in the same site (8-bit PNG)
    :input qty "How many?"                        a text field; the value is kept on YOUR machine only
    :check paid "Already paid"                    a tick box
    :calc total "Total" = price * qty + 2         a number computed from fields (+ - * / // % **, round, min, max, abs)

Everything is declarative: the publisher ships text, the reader's client does the arithmetic with a tiny
safe evaluator (no eval, no names except the fields). Because it is only data, forms work offline from the
local copy, and cannot run anything on the reader's machine."""
import ast, operator, re
from . import gfx

IMG = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
INPUT = re.compile(r'^:input\s+(\w+)\s+"([^"]*)"\s*$')
CHECK = re.compile(r'^:check\s+(\w+)\s+"([^"]*)"\s*$')
CALC = re.compile(r'^:calc\s+(\w+)\s+"([^"]*)"\s*=\s*(.+?)\s*$')
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
FUNCS = {"round": round, "min": min, "max": max, "abs": abs}
MAX_EXP = 12


def blocks(lines):
    """Lines -> [("text", line) | ("image", alt, path) | ("input", name, label) | ("check", ...) | ("calc", name, label, expr)]"""
    out = []
    for ln in lines:
        for kind, rx in (("image", IMG), ("input", INPUT), ("check", CHECK), ("calc", CALC)):
            m = rx.match(ln)
            if m:
                out.append((kind,) + m.groups())
                break
        else:
            out.append(("text", ln))
    return out


def fields(bl):
    """Names of the things a reader can edit, in page order."""
    return [(b[0], b[1]) for b in bl if b[0] in ("input", "check")]


def _num(v):
    try:
        return float(str(v).strip() or 0)
    except ValueError:
        return float("nan")


def evaluate(expr, values):
    """Safe arithmetic over the page's fields. Returns a float, or None if the expression is not valid."""
    def go(n):
        if isinstance(n, ast.Expression):
            return go(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            return _num(values.get(n.id, ""))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = go(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            a, b = go(n.left), go(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > MAX_EXP:
                raise ValueError("exponent too large")
            return OPS[type(n.op)](a, b)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return float(FUNCS[n.func.id](*[go(a) for a in n.args]))
        raise ValueError("not allowed")
    try:
        return go(ast.parse(expr, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError, OverflowError):
        return None


def fmt(v):
    if v is None or v != v:
        return "?"
    return ("%d" % v) if v == int(v) and abs(v) < 1e15 else ("%.4f" % v).rstrip("0").rstrip(".")


def render(bl, values, focus, store, sid, width, image_rows=10, cache=None):
    """Blocks -> display lines. Lines starting with "\\x00" are pre-formatted (not wrapped or restyled)."""
    BOLD, DIM, REV, RESET, GOLD = "\033[1m", "\033[2m", "\033[7m", "\033[0m", "\033[38;2;255;220;100m"
    out, names = [], [b[1] for b in bl if b[0] in ("input", "check")]
    for b in bl:
        kind = b[0]
        if kind == "text":
            out.append(b[1])
        elif kind == "input":
            name, label = b[1], b[2]
            val = values.get(name, "")
            on = focus is not None and names[focus] == name
            box = (REV + (val or " ") + " " * max(0, 14 - len(val)) + RESET) if on else (
                DIM + "[" + RESET + val.ljust(14) + DIM + "]" + RESET)
            out.append("\x00  %s: %s" % (label, box))
        elif kind == "check":
            name, label = b[1], b[2]
            on = focus is not None and names[focus] == name
            mark = "[x]" if values.get(name) else "[ ]"
            out.append("\x00  " + (REV if on else "") + mark + " " + label + RESET)
        elif kind == "calc":
            out.append("\x00  %s: %s%s%s" % (b[2], BOLD + GOLD, fmt(evaluate(b[3], values)), RESET))
        elif kind == "image":
            alt, path = b[1], b[2]
            key = (sid, path, width, image_rows)
            if cache is not None and key in cache:
                rows = cache[key]
            else:
                rows = None
                try:
                    body = store.info(sid)
                    if body and path in body["files"]:
                        rows = gfx.render_png(store.read(sid, path), max(10, width - 4), image_rows)
                except Exception:
                    rows = None
                if cache is not None:
                    cache[key] = rows
            if rows:
                out += ["\x00  " + r for r in rows]
            else:
                out.append("\x00  " + DIM + "[image: %s]" % (alt or path) + RESET)
    return out
