"""A walkable first-person 3D view of the network, rendered in the terminal with a raycaster (the technique
Doom-era games used). Each site you hold, or have a name for, is a door in the walls; walk up to one and
press Enter to open it. Pure standard library: see gfx.py for the half-block pixel output."""
import math, shutil, sys
from . import gfx, site as sitelib

MAP = [
    "#1##2##3##4##5###",
    "#...............#",
    "6.....#######...7",
    "#.....#.....#...#",
    "#.....#.....#...#",
    "8.....###.###...9",
    "#...............#",
    "#...............#",
    "#################",
]
DOOR_HUES = [(255, 190, 60), (90, 220, 255), (240, 90, 220), (120, 255, 150), (255, 110, 90),
             (160, 140, 255), (255, 240, 120), (90, 255, 220), (255, 150, 200)]
FOV = math.pi / 3
MOVE, TURN = 0.3, 0.16


def _brick(u, v):
    row = int(v * 8)
    off = 0.5 if row % 2 else 0.0
    bu = (u * 4 + off) % 1.0
    if (v * 8) % 1.0 < 0.1 or bu < 0.06:
        return (55, 38, 36)
    shade = 0.85 + 0.3 * (((int(u * 4 + off) * 31 + row * 17) % 7) / 7.0)
    return (int(150 * shade), int(72 * shade), int(58 * shade))


def _door(u, v, hue):
    edge = min(u, 1 - u, v, 1 - v)
    if edge < 0.09:
        return hue
    glow = 0.35 + 0.65 * (1 - abs(u - 0.5) * 2) * (1 - abs(v - 0.5) * 1.2)
    return (int(hue[0] * 0.5 * glow + 12), int(hue[1] * 0.5 * glow + 12), int(hue[2] * 0.5 * glow + 18))


class World:
    def __init__(self, doors):
        """doors: list of (label, ref) for up to 9 doors."""
        self.doors = doors[:9]
        self.x, self.y, self.a = 4.5, 6.5, -math.pi / 2

    def cell(self, cx, cy):
        if 0 <= cy < len(MAP) and 0 <= cx < len(MAP[0]):
            return MAP[cy][cx]
        return "#"

    def step(self, dist):
        nx, ny = self.x + math.cos(self.a) * dist, self.y + math.sin(self.a) * dist
        if self.cell(int(nx), int(self.y)) == ".":
            self.x = nx
        if self.cell(int(self.x), int(ny)) == ".":
            self.y = ny

    def turn(self, d):
        self.a = (self.a + d) % (2 * math.pi)

    def cast(self, ang):
        """Return (distance, hit_cell_char, side, texture_u) for a ray at world angle `ang`."""
        dx, dy = math.cos(ang), math.sin(ang)
        mx, my = int(self.x), int(self.y)
        ddx, ddy = abs(1 / dx) if dx else 1e30, abs(1 / dy) if dy else 1e30
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        sdx = ((mx + 1 - self.x) if dx > 0 else (self.x - mx)) * ddx
        sdy = ((my + 1 - self.y) if dy > 0 else (self.y - my)) * ddy
        side = 0
        for _ in range(64):
            if sdx < sdy:
                sdx += ddx; mx += sx; side = 0
            else:
                sdy += ddy; my += sy; side = 1
            c = self.cell(mx, my)
            if c != ".":
                d = (sdx - ddx) if side == 0 else (sdy - ddy)
                hx, hy = self.x + dx * d, self.y + dy * d
                u = (hy if side == 0 else hx) % 1.0
                return max(d, 0.01), c, side, u
        return 64.0, "#", 0, 0.0

    def facing_door(self):
        d, c, _, _ = self.cast(self.a)
        if c.isdigit() and d < 2.2 and int(c) - 1 < len(self.doors) and c != "0":
            return int(c) - 1
        return None

    def render(self, w, h):
        """Return h rows x w columns of (r, g, b) pixels."""
        rows = [[(0, 0, 0)] * w for _ in range(h)]
        half = h / 2
        for x in range(w):
            ang = self.a + (x / w - 0.5) * FOV
            d, c, side, u = self.cast(ang)
            d *= math.cos(ang - self.a)                    # remove fisheye
            hgt = min(h * 3, int(h / max(d, 0.05)))
            top = int(half - hgt / 2)
            fog = 1.0 / (1.0 + d * 0.22) * (0.72 if side else 1.0)
            hue = DOOR_HUES[(int(c) - 1) % 9] if c.isdigit() and c != "0" else None
            for y in range(h):
                if y < top:
                    t = y / half
                    rows[y][x] = (int(14 + 18 * t), int(16 + 26 * t), int(40 + 36 * t))
                elif y >= top + hgt:
                    t = (y - half) / half
                    rows[y][x] = (int(22 + 40 * t), int(20 + 36 * t), int(24 + 30 * t))
                else:
                    v = (y - top) / max(hgt, 1)
                    base = _door(u, v, hue) if hue else _brick(u, v)
                    rows[y][x] = (int(base[0] * fog), int(base[1] * fog), int(base[2] * fog))
        return rows

    def frame(self, cols, cell_rows):
        """The whole screen as lines: the 3D view plus a HUD."""
        lines = gfx.halfblocks(self.render(cols, cell_rows * 2))
        door = self.facing_door()
        if door is not None:
            label = self.doors[door][0]
            hud = "\033[1m\033[38;2;255;220;100m  Enter: open  %s\033[0m" % label
        else:
            hud = "\033[2m  walk up to a glowing door\033[0m"
        keys = "\033[2m  [arrows/wasd] move  [enter] open door  [q] leave\033[0m"
        return lines + [hud, keys]


def play(world, getkey, write, size):
    """Run the walk-around loop. getkey(timeout)->str|None, write(str), size()->(cols, rows).
    Returns the chosen door's ref, or None if the player left."""
    write("\033[?25l")
    try:
        while True:
            cols, rows = size()
            cols, cell_rows = max(40, min(cols, 110)), max(8, min(rows - 2, 34))
            write("\033[H" + "\r\n".join(ln + "\033[K" for ln in world.frame(cols, cell_rows)))
            k = getkey(0.5)
            if k in ("q", "quit", "esc"):
                return None
            if k in ("up", "w", "k"): world.step(MOVE)
            elif k in ("down", "s", "j"): world.step(-MOVE)
            elif k in ("left", "a"): world.turn(-TURN)
            elif k in ("right", "d"): world.turn(TURN)
            elif k == "enter":
                door = world.facing_door()
                if door is not None:
                    return world.doors[door][1]
    finally:
        write("\033[?25h")


def doors_for(home):
    """Doors = your petnames first, then sites in your store (one door each, labelled by name)."""
    seen, doors = set(), []
    for name, ref in sorted(home.names().items()):
        doors.append((name, ref))
        seen.add(ref.split("@")[0])
    store = home.store()
    for sid in store.sites():
        if sid in seen:
            continue
        info = store.info(sid)
        doors.append((sitelib.display_name(info), sid))
    return doors


def run_standalone(home):
    """`alternet world`: raw-mode wrapper around play(). Returns the chosen ref or None."""
    import termios, tty
    from .tui import RawAnsiBrowser
    doors = doors_for(home)
    if not doors:
        raise SystemExit("No sites to show yet. Try: alternet start")
    getkey = RawAnsiBrowser(None)._getkey
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sys.stdout.write("\033[?1049h\033[2J")
    try:
        tty.setraw(fd)
        return play(World(doors), getkey, lambda s: (sys.stdout.write(s), sys.stdout.flush()),
                    lambda: tuple(shutil.get_terminal_size(fallback=(80, 24))))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
