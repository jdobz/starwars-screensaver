#!/usr/bin/env python3
"""
starwars_screensaver.py - a Star Wars take on asciiquarium.

Top 75% of the terminal: a space battle - TIE fighters, X-wings, Y-wings,
Star Destroyers, the Millennium Falcon, laser bolts, explosions, drifting
wreckage - and a Death Star that now and then fires its superlaser.
Bottom 25%: a desert world - AT-ATs, AT-STs, speeder bikes, R2-D2, C-3PO,
Jedi, Yoda, Ewoks and stormtroopers (with blaster sparks).

Pure Python standard library (curses). Works on macOS / Linux terminals.

Keys:  q = quit   r = redraw   p = pause   s = superlaser   f = Falcon
       x = torpedo run on the Death Star (rare on its own)
       c = Razor Crest flyby

All sprites are original, simplified ASCII drawings.
"""

import argparse
import curses
import math
import random
import time

MIN_W, MIN_H = 60, 20
GROUND_FRAC = 0.25   # share of the screen height used by the ground
MAX_PARTICLES = 220  # cap on debris / spark particles

# --------------------------------------------------------------------------
# Sprites
# --------------------------------------------------------------------------
# Art conventions:  ' ' = transparent,  '?' = opaque space.
# Masks: a letter per cell picks a colour (r g y b m c w; UPPER = bold),
# ' ' = the entity's own colour, 's' = the entity's saber colour.

FLIP = str.maketrans("/\\()<>[]{}db", "\\/)(><][}{bd")


def art(s):
    return s.strip("\n").split("\n")


class Sprite:
    def __init__(self, lines, mask=None):
        self.lines = lines
        self.mask = mask
        self.h = len(lines)
        self.w = len(lines[0]) if lines else 0


class Art:
    """A set of animation frames, prebuilt facing right (1) and left (-1)."""

    def __init__(self, frames, masks=None):
        w = max(len(l) for f in frames for l in f)
        h = max(len(f) for f in frames)
        self.w, self.h = w, h

        def pad(f):
            return [l.ljust(w) for l in f] + [" " * w] * (h - len(f))

        right, left = [], []
        for i, f in enumerate(frames):
            f = pad(f)
            m = pad(masks[i]) if masks else None
            right.append(Sprite(f, m))
            left.append(Sprite([l[::-1].translate(FLIP) for l in f],
                               [l[::-1] for l in m] if m else None))
        self.sprites = {1: right, -1: left}
        self.n = len(frames)


def paint(lines, rules):
    """Build a colour mask: rules = [(row0, row1, col0, col1, letter), ...]
    paints every non-space cell inside the box; later rules win."""
    mask = [[" "] * len(l) for l in lines]
    for r0, r1, c0, c1, ch in rules:
        for r in range(r0, min(r1 + 1, len(lines))):
            for c in range(c0, min(c1 + 1, len(lines[r]))):
                if lines[r][c] != " ":
                    mask[r][c] = ch
    return ["".join(m) for m in mask]


def build_star_destroyer(half, length):
    """Procedural Imperial Star Destroyer (top-down, bow to the right).
    Returns (lines, mask, turret positions).
    half = rows above/below the centre line, length = hull length in cols.
    Returns (lines, mask) - mask letters: z/Z = grey hull/detail, c = engines,
    W = bridge tower."""
    ox = 3                                   # hull starts after the engines
    H, Wd = 2 * half + 3, length + ox + 1
    cy = half + 1
    ch = [[" "] * Wd for _ in range(H)]
    co = [[" "] * Wd for _ in range(H)]

    def L(dy):                               # hull length on row dy
        t = abs(dy) / (half + 0.6)
        n = (length - 1) * (1 - t)
        n -= 0.025 * length * ((t > 0.33) + (t > 0.66))   # stepped edge notches
        return max(3, int(round(n)))

    def put_(r, c, s, k=None):
        if 0 <= r < H and 0 <= c < Wd:
            ch[r][c] = s
            if k:
                co[r][c] = k

    for dy in range(-half, half + 1):
        r, ln = cy + dy, L(dy)
        for c in range(ln + 1):
            put_(r, ox + c, "?", "z")
        put_(r, ox, "|", "Z")                # stern wall
        put_(r, ox + ln, ">" if dy == 0 else ("\\" if dy < 0 else "/"), "Z")
        if dy < 0:                           # upper edge runs, drawn above
            for c in range(L(dy - 1) + 1 if dy > -half else 1, ln):
                put_(r - 1, ox + c, "_", "Z")
        elif dy > 0:                         # lower edge runs, in the row
            for c in range(L(dy + 1) + 1 if dy < half else 1, ln):
                put_(r, ox + c, "_", "Z")
    # hull plating: staggered panel seams, speckle and a keel line;
    # the upper half is lit (lighter) and the lower half in shadow
    rnd = random.Random(21)
    for dy in range(-half + 1, half):
        r, tone = cy + dy, ("Z" if dy < 0 else "z")
        for c in range(3, L(dy) - 2):
            if ch[r][ox + c] != "?":
                continue
            if (c + 5 * (dy % 2)) % 10 == 0 and rnd.random() < 0.75:
                put_(r, ox + c, "|", tone)           # brick-pattern seams
            elif dy % 3 == 0 and c % 10 in (2, 3, 4) and rnd.random() < 0.6:
                put_(r, ox + c, "-", tone)
            elif rnd.random() < 0.05:
                put_(r, ox + c, rnd.choice(".:'`"), tone)
    for c in range(2, L(0) - 2):             # keel line
        if ch[cy][ox + c] == "?":
            put_(cy, ox + c, "=" if c % 2 else "-", "Z")
    # command superstructure at the stern
    bh = max(2, int(half * 0.6))
    sx0, sx1 = ox + 5, ox + 5 + max(8, int(length * 0.2))
    for dy in range(-bh, bh + 1):
        for c in range(sx0, sx1 + 1):
            edge_r, edge_c = dy in (-bh, bh), c in (sx0, sx1)
            if edge_r and edge_c:
                put_(cy + dy, c, "+", "Z")
            elif edge_r:
                put_(cy + dy, c, "=", "Z")
            elif edge_c:
                put_(cy + dy, c, "|", "Z")
            else:
                put_(cy + dy, c, ":" if (c + dy) % 3 == 0 else "?", "z")
    tw = max(1, bh // 2)                     # bridge tower + shield domes
    for dy in range(-tw, tw + 1):
        for c in range(sx0 + 2, sx0 + 7):
            put_(cy + dy, c, "#", "W")
    for dy in (-tw - 1, tw + 1):
        for i, s in enumerate("(o)"):
            put_(cy + dy, sx0 + 3 + i, s, "W")
    # raised deck panels, drawn as outlines on the open hull
    plating = "?|-:.'`"

    def free(r, c):
        return 0 <= r < H and 0 <= c < Wd and ch[r][c] in plating

    ph = 2 if half < 6 else 3
    for _ in range(max(3, half)):
        pw = rnd.randint(6, 11)
        r0 = rnd.randint(cy - half + 1, cy + half - ph - 1)
        c0 = rnd.randint(ox + int(length * 0.25), ox + int(length * 0.8) - pw)
        cells = ([(r0, c0 + i) for i in range(pw)] +
                 [(r0 + ph - 1, c0 + i) for i in range(pw)] +
                 [(r0 + j, c0) for j in range(ph)] +
                 [(r0 + j, c0 + pw - 1) for j in range(ph)])
        if not all(free(r, c) for r, c in cells):
            continue
        tone = "Z" if r0 + ph // 2 < cy else "z"
        for i in range(pw):
            put_(r0, c0 + i, "+" if i in (0, pw - 1) else "-", tone)
            put_(r0 + ph - 1, c0 + i, "+" if i in (0, pw - 1) else "-", tone)
        for j in range(1, ph - 1):
            put_(r0 + j, c0, "|", tone)
            put_(r0 + j, c0 + pw - 1, "|", tone)
    turrets = []                             # (row, col) of every gun
    for sign in (-1, 1):                     # banks of four turrets, stern
        dy = sign * (bh + 2)
        if abs(dy) < half - 1:
            for i in range(4):
                c = ox + 6 + 4 * i
                if c - ox + 3 < L(dy) - 1:
                    for j, s in enumerate("(o)"):
                        put_(cy + dy, c + j, s, "W")
                    turrets.append((cy + dy, c + 1))
    for sign in (-1, 1):                     # gun turrets along the flanks
        for frac_row in (0.4, 0.7):
            dy = sign * max(2, int(round(half * frac_row)))
            for frac in (0.12, 0.3, 0.5):
                c = ox + int(length * frac)
                r = cy + dy
                if (c - ox + 5 < L(dy) - 1 and
                        all(free(r, c + j) for j in range(3))):
                    put_(r, c, "{+}", "W")
                    turrets.append((r, c + 1))
    # engines: tall 3x3 blocks of bright blue glow at the stern
    if half >= 5:
        off = min(half - 1, max(4, half * 2 // 3))
        centres = (-off, 0, off)
    else:                                    # small terminal: one engine
        centres = (0,)
    for dy in centres:
        for r in range(-1, 2):               # 2 cols + the stern wall = |||
            for c in (1, 2, ox):
                put_(cy + dy + r, c, "|", "E")
    return ["".join(r) for r in ch], ["".join(r) for r in co], turrets


def build_falcon(W=25, H=10):
    """Top-down Millennium Falcon, bow (mandibles) to the right."""
    rnd = random.Random(7)                   # fixed texture
    ch = [[" "] * W for _ in range(H)]
    co = [[" "] * W for _ in range(H)]
    cx, cy, rx, ry = 9.0, 4.5, 8.5, 4.7

    def inside(c, r):
        return ((c - cx) / rx) ** 2 + ((r - cy) / ry) ** 2 <= 1.0

    def put_(r, c, s, k="z"):
        if 0 <= r < H and 0 <= c < W:
            ch[r][c], co[r][c] = s, k

    for r in range(H):                       # the saucer
        for c in range(W):
            if inside(c, r):
                put_(r, c, ".:" [rnd.random() < 0.5] if rnd.random() < 0.07
                     else "?", "z")
    for r in range(H):                       # its outline
        for c in range(W):
            if not inside(c, r):
                continue
            l, rt = not inside(c - 1, r), not inside(c + 1, r)
            u, dn = not inside(c, r - 1), not inside(c, r + 1)
            if not (l or rt or u or dn):
                continue
            s = ("/" if l and u else "\\" if l and dn else
                 "\\" if rt and u else "/" if rt and dn else
                 "(" if l else ")" if rt else "=")
            put_(r, c, s, "W")
    n = W - 15                               # the two mandibles
    for i in range(n):
        c = 15 + i
        top, bot = 1 + (i * 2) // (n - 1), 8 - (i * 2) // (n - 1)
        for r in range(top, 4):
            put_(r, c, "?", "z")
        for r in range(6, bot + 1):
            put_(r, c, "?", "z")
        put_(top, c, "=" if top < 3 else "_", "W")
        put_(3, c, "_", "W")
        put_(6, c, "=", "W")
        put_(bot, c, "_" if bot > 6 else "=", "W")
    put_(3, W - 1, ">", "W")
    put_(6, W - 1, ">", "W")
    for i, s in enumerate("[=:=:=:=]"):      # central boarding pod
        put_(4, 11 + i, s, "Z")
    for i, s in enumerate("[_:_:_:_]"):
        put_(5, 11 + i, s, "Z")
    for r, c0 in ((3, 10), (2, 11), (1, 12)):    # offset cockpit tube
        put_(r, c0, "/", "W")
        put_(r, c0 + 1, "/", "W")
    for i, s in enumerate("[=]"):
        put_(0, 14 + i, s, "W")
    for i, s in enumerate("(@)"):            # dish
        put_(4, 8 + i, s, "W")
    for i, s in enumerate("'-'"):
        put_(5, 8 + i, s, "W")
    for i, s in enumerate("[|]"):            # lower hatch
        put_(7, 8 + i, s, "Z")
    for r in (2, 4, 6):                      # engine grills right at the stern
        c0 = min(c for c in range(W) if inside(c, r))
        for i, s in enumerate("(@@)"):
            put_(r, c0 + i, s, "E")
    return ["".join(r) for r in ch], ["".join(r) for r in co]


_FALCON_LINES, _FALCON_MASK = build_falcon()
FALCON = Art([_FALCON_LINES], [_FALCON_MASK])

def build_atat():
    """Side-profile AT-AT walker, head to the right. Returns two walking
    frames as ([lines], [mask]) pairs."""
    W, H = 41, 13
    rnd = random.Random(5)

    def put_(g, r, c, s, k="Z"):
        for i, x in enumerate(s):
            if x != "~" and 0 <= r < H and 0 <= c + i < W:
                g[0][r][c + i], g[1][r][c + i] = x, k

    def body(g):
        put_(g, 0, 8, "_" * 12)
        put_(g, 1, 5, "__/" + "?" * 12 + "\\__")
        put_(g, 2, 3, "_/" + "?" * 18 + "\\_")
        for r in (3, 4):
            put_(g, r, 2, "|" + "?" * 22 + "|")
        for r in range(1, 5):                      # panel seams
            put_(g, r, 8, "|", "W")
            put_(g, r, 18, "|", "W")
        for r in range(1, 5):                      # plating texture
            for c in range(3, 24):
                if g[0][r][c] == "?" and rnd.random() < 0.07:
                    put_(g, r, c, rnd.choice(":,.'"), "z")
        put_(g, 5, 2, "[" + "=" * 22 + "]")         # belly plate
        put_(g, 3, 26, "||||", "W")                # ribbed neck
        put_(g, 4, 26, "||||", "W")
        put_(g, 2, 32, "______")                   # head
        put_(g, 3, 30, "/??(O)??\\__")
        put_(g, 3, 33, "(O)", "R")
        put_(g, 4, 30, "\\_______/=>")
        put_(g, 4, 41 - 1, ">", "W")

    def leg(g, hc, shape, k):
        o = {"S": 0, "F": 1, "B": -1}[shape]
        put_(g, 6, hc, "(O)", "W")                 # hip
        put_(g, 7, hc, {"S": "| |", "F": "\\ \\", "B": "/ /"}[shape], k)
        put_(g, 8, hc + o, "(o)", "W")             # knee
        put_(g, 9, hc + o, "| |", k)
        put_(g, 10, hc + o, "| |", k)
        put_(g, 11, hc + o, "[=]", "W")            # ankle
        put_(g, 12, hc + o - 1, "/===\\", k)       # foot

    frames = []
    for shapes in (("B", "S", "F", "S"), ("S", "F", "S", "B")):
        g = ([[" "] * W for _ in range(H)], [[" "] * W for _ in range(H)])
        body(g)
        # far legs first (darker), then the near legs on top
        leg(g, 9, shapes[1], "z")
        leg(g, 16, shapes[2], "z")
        leg(g, 5, shapes[0], "Z")
        leg(g, 20, shapes[3], "Z")
        frames.append((["".join(r) for r in g[0]], ["".join(r) for r in g[1]]))
    return frames


_ATAT_FRAMES = build_atat()
ATAT = Art([f[0] for f in _ATAT_FRAMES], [f[1] for f in _ATAT_FRAMES])

def build_atst():
    """Side-profile AT-ST, head to the right: a small boxy cab with a slit
    window near the top and one chin cannon, on reverse-jointed legs (hip,
    long thigh straight back to the 'knee', straight shin down to the
    'ankle', then a short slope forward to the foot).
    Returns two walking frames as ([lines], [mask]) pairs."""
    W, H = 23, 12
    rnd = random.Random(9)

    def put_(g, r, c, s, k="Z"):
        for i, x in enumerate(s):
            if x != "~" and 0 <= r < H and 0 <= c + i < W:
                g[0][r][c + i], g[1][r][c + i] = x, k

    def body(g):
        put_(g, 0, 6, "_" * 7)                       # roof
        put_(g, 1, 5, "|" + "?" * 7 + "\\")           # front leans forward
        put_(g, 2, 5, "|" + "?" * 8 + "\\")
        put_(g, 3, 5, "\\" + "_" * 8 + "/")          # floor of the cab
        put_(g, 1, 9, "===", "R")                    # slit window, near the top
        for r in (1, 2):                             # a little plating
            for c in (6, 7, 8, 12):
                if rnd.random() < 0.45:
                    put_(g, r, c, rnd.choice(":,."), "z")
        put_(g, 3, 15, "=====>", "W")                # single chin cannon

    def lower_leg(g, knee, lifted, k):
        """knee column = centre of the knee joint (row 5)."""
        put_(g, 5, knee - 1, "(o)", "W")             # knee
        drop = 2 if lifted else 3                    # straight shin
        for r in range(6, 6 + drop):
            put_(g, r, knee - 1, "|?|", k)
        ar = 6 + drop
        put_(g, ar, knee - 1, "(o)", "W")            # ankle
        put_(g, ar + 1, knee, "\\?\\", k)            # slopes forward...
        put_(g, ar + 2, knee, "/===\\", k)           # ...to the foot

    frames = []
    for near_lift, far_lift in ((False, True), (True, False)):
        g = ([[" "] * W for _ in range(H)], [[" "] * W for _ in range(H)])
        body(g)
        lower_leg(g, 8, far_lift, "z")               # far leg, behind
        # near thigh: from the hip at the centre of the cab's underside,
        # almost straight back to the knee
        put_(g, 4, 9, "(O)", "W")
        put_(g, 4, 5, "_" * 4)
        put_(g, 4, 4, "/")
        lower_leg(g, 3, near_lift, "Z")
        frames.append((["".join(r) for r in g[0]], ["".join(r) for r in g[1]]))
    return frames


_ATST_FRAMES = build_atst()
ATST = Art([f[0] for f in _ATST_FRAMES], [f[1] for f in _ATST_FRAMES])

def build_death_star(rx=9, ry=4, seed=11):
    rows = []
    for dy in range(-ry, ry + 1):
        hw = int(round(rx * math.sqrt(max(0.0, 1 - (dy / (ry + 0.6)) ** 2))))
        n = 2 * hw - 1
        if dy == -ry:
            left, mid, right = ".", "-" * n, "."
        elif dy == ry:
            left, mid, right = "'", "-" * n, "'"
        elif dy == 0:
            left, mid, right = "(", "-" * n, ")"
        elif dy < 0:
            left, mid, right = "/", "?" * n, "\\"
        else:
            left, mid, right = "\\", "?" * n, "/"
        rows.append([" "] * (rx - hw) + list(left + mid + right))
    # super-laser dish, upper right - scaled to the sphere
    rd = max(1, int(ry * 0.25))
    dc_row = ry - max(2, int(round(ry * 0.5)))     # centre row index
    dc_col = rx + int(round(rx * 0.30))            # centre column index
    for dyd in range(-rd, rd + 1):
        hwd = max(2, int(round(2 * rd * math.sqrt(
            max(0.0, 1 - (dyd / (rd + 0.6)) ** 2)))))
        n = 2 * hwd - 1
        if dyd == -rd:
            cells = list("." + "-" * n + ".")
        elif dyd == rd:
            cells = list("'" + "-" * n + "'")
        else:
            cells = ["("] + ["?"] * n + [")"]
            if rd >= 3:      # concentric ring inside bigger dishes
                for k in range(n):
                    dx = (k - (n - 1) / 2.0) / (2.0 * (rd + 0.6))
                    dd = math.sqrt(dx * dx + (dyd / (rd + 0.6)) ** 2)
                    if 0.45 < dd < 0.62:
                        cells[1 + k] = ":"
            if dyd == 0:
                cells[1 + n // 2] = "O" if rd >= 3 else "o"
        r = rows[dc_row + dyd]
        start = dc_col - hwd
        for j, ch in enumerate(cells):
            idx = start + j
            if 0 < idx < len(r) - 1 and r[idx] != " ":
                r[idx] = ch
    # surface texture: grooves, panels, a crater and speckle (fixed seed)
    rng = random.Random(seed)
    mask = [[" "] * len(r) for r in rows]

    def free(r, c, n=1):
        return (0 <= r < len(rows) and
                all(0 <= c + i < len(rows[r]) and rows[r][c + i] == "?"
                    for i in range(n)))

    def put_(r, c, s, k="z"):
        for i, x in enumerate(s):
            rows[r][c + i], mask[r][c + i] = x, k

    for c in range(len(rows[ry])):               # equatorial trench
        if rows[ry][c] == "-":
            rows[ry][c], mask[ry][c] = "=", "Z"
    if ry >= 6:
        for dy in (-int(round(ry * 0.55)), int(round(ry * 0.55))):
            r = ry + dy                          # latitude grooves
            for c in range(len(rows[r])):
                if free(r, c) and c % 7 < 5:
                    put_(r, c, "-")
        for _ in range(ry):                      # small surface panels
            r, c = rng.randint(1, 2 * ry - 1), rng.randint(2, 2 * rx - 4)
            if free(r, c, 3) and abs(r - ry) > 1:
                put_(r, c, rng.choice(("[:]", "|_|", "[=]", "<#>")))
    if ry >= 7:                                  # a crater, lower left
        r, c = ry + 2, max(3, rx // 2)
        if all(free(r + i, c, 5) for i in (-1, 0, 1)):
            put_(r - 1, c, "?.-.?")
            put_(r, c, "(???)")
            put_(r + 1, c, "?'-'?")
    for r in range(len(rows)):                   # speckle
        for c in range(len(rows[r])):
            if free(r, c) and rng.random() < 0.13:
                put_(r, c, rng.choice(".:`',"))
    return ["".join(r) for r in rows], ["".join(m) for m in mask], dc_col, dc_row


TIE = Art([art(r"""
|\ /|
|-O-|
|/ \|
""")])

_XWING = art(r"""
   [==]----+
  /   |
=-[==]|____.
(######(o)[::]--->
=-[==]|''''.
  \   |
   [==]----+
""")
XWING = Art([_XWING], [paint(_XWING, [
    (0, 0, 3, 10, "z"), (6, 6, 3, 10, "z"),     # cannon pods and rods
    (0, 0, 11, 11, "Y"), (6, 6, 11, 11, "Y"),   # cannon tips
    (1, 1, 2, 6, "R"), (5, 5, 2, 6, "R"),       # red wing panels...
    (1, 1, 6, 6, "y"), (5, 5, 6, 6, "y"),       # ...with a tan edge
    (2, 2, 0, 5, "z"), (4, 4, 0, 5, "z"),       # engine pods + nozzles
    (2, 2, 7, 11, "r"), (4, 4, 7, 11, "r"),     # red fuselage stripes
    (3, 3, 0, 0, "z"),                          # rear thruster
    (3, 3, 8, 8, "R"),                          # R2 unit
    (3, 3, 10, 13, "c"),                        # cockpit canopy
    (3, 3, 17, 17, "z"),                        # nose tip
])])

YWING = Art([art(r"""
[=====]
   ======[o>
[=====]
""")])

TROOPER = Art(
    [[" [=]  ", "-|#|==", " |#|  ", " / \\  "],
     [" [=]  ", "-|#|==", " |#|  ", " | |  "]],
    [["      ", "    cc", "      ", "      "]] * 2,
)

YODA = Art(
    [[" \\_._/ ", " (o.o) ", "  /|\\ |", "  / \\ |"],
     [" \\_._/ ", " (o.o) ", "  /|\\ |", "  | | |"]],
    [["       ", "       ", "      y", "      y"]] * 2,
)

EWOK = Art([
    [" .^. ", "(o.o)", " / \\ "],
    [" .^. ", "(o.o)", " |_| "],
])

DEBRIS_SPIN = Art([["-"], ["\\"], ["|"], ["/"]])
DEBRIS_CHUNK = Art([["+"], ["x"], ["*"], ["x"]])

BOLT = Art([["=="]])

EXPLOSION = Art([
    ["     ", "     ", "  *  ", "     ", "     "],
    ["     ", "  .  ", " -*- ", "  '  ", "     "],
    ["  |  ", " \\|/ ", "--O--", " /|\\ ", "  |  "],
    [" . ' ", "'  .'", " .  .", "'. ' ", " '.  "],
    ["     ", ".   '", "  .  ", "'   .", "     "],
])

_SPEEDER = art(r"""
 .-----.            _.--._
(=======)\        .'      '.
   '-.__  \_______/'--------'--.___
     (=====)===[::::::::::::]===+==>
      '-._____________________..-'
""")
SPEEDER = Art([_SPEEDER], [paint(_SPEEDER, [
    (0, 2, 0, 11, "w"),      # grey engine pods...
    (0, 2, 2, 9, "r"),       # ...with a red stripe
    (3, 4, 5, 12, "w"),      # lower engine
    (3, 3, 7, 11, "r"),
    (0, 2, 19, 29, "c"),     # glass canopy
])])

_C3PO_TOP = [
    "  .---.  ",
    "  |o_o|  ",
    "  '-=-'  ",
    " .-[#]-. ",
    "/| (@) |\\",
    "| |===| |",
    "| |___| |",
    "  |_|_|  ",
]
_C3PO_A = _C3PO_TOP + ["  || ||  ", " _|| ||_ "]
_C3PO_B = _C3PO_TOP + ["  |/ \\|  ", " _/   \\_ "]
C3PO = Art([_C3PO_A, _C3PO_B], [paint(f, [
    (1, 1, 3, 3, "o"), (1, 1, 5, 5, "o"),       # glowing eyes
    (4, 4, 3, 5, "o"),                           # chest dial
]) for f in (_C3PO_A, _C3PO_B)])

_R2_TOP = [
    "  .-=-.  ",
    " /[]:[]\\ ",
    "|==(O)==|",
    "|[=]|[=]|",
    "|_______|",
]
_R2_A = _R2_TOP + ["[_]   [_]"]
_R2_B = _R2_TOP + [" [_] [_] "]
R2D2 = Art([_R2_A, _R2_B], [paint(f, [
    (0, 0, 4, 4, "B"), (1, 1, 2, 6, "B"),       # blue dome panels
    (2, 2, 1, 2, "B"), (2, 2, 6, 7, "B"),       # blue band
    (2, 2, 3, 5, "R"),                           # eye
    (3, 3, 1, 3, "B"), (3, 3, 5, 7, "B"),       # blue body panels
]) for f in (_R2_A, _R2_B)])

def build_razor():
    """Top-down Razor Crest, nose to the right: yellow cockpit with tan
    stripes and two forward guns, a wide hull, and two big engine pods with
    orange vents on pylons."""
    W, H = 28, 10
    rnd = random.Random(3)
    ch = [[" "] * W for _ in range(H)]
    co = [[" "] * W for _ in range(H)]

    def put_(r, c, s, k="Z"):
        for i, x in enumerate(s):
            if x != "~" and 0 <= r < H and 0 <= c + i < W:
                ch[r][c + i], co[r][c + i] = x, k

    def outline(inside, k):
        """fill a region with opaque hull and draw its outline."""
        for r in range(H):
            for c in range(W):
                if inside(c, r):
                    put_(r, c, "?", "z")
        for r in range(H):
            for c in range(W):
                if not inside(c, r):
                    continue
                l, rt = not inside(c - 1, r), not inside(c + 1, r)
                u, d = not inside(c, r - 1), not inside(c, r + 1)
                if not (l or rt or u or d):
                    continue
                s = ("." if (l or rt) and u else "'" if (l or rt) and d else
                     "(" if l else ")" if rt else "-")
                put_(r, c, s, k)

    def hull(c, r):                          # tail, wide body, neck + nose
        if 4 <= r <= 5 and 0 <= c <= 27:
            return True
        return 3 <= r <= 6 and 5 <= c <= 19

    def engine(c, r):                        # rounded pod
        return 6 <= c <= 17 and (0 <= r <= 2 or 7 <= r <= 9)

    outline(hull, "Z")
    outline(engine, "z")
    for r in (1, 8):                         # engine details
        put_(r, 10, "[::]", "Z")
        put_(r, 18, "=", "z")
        put_(r, 3, "|||", "O")               # orange vents at the stern
    for r in (2, 7):                         # pylons to the hull
        put_(r, 9, "[==]", "Z")
    put_(4, 9, ".----.", "Z")                # dorsal hatch
    put_(5, 9, "(o--o)", "Z")
    put_(4, 0, "[=]", "z")                   # tail plate
    put_(5, 0, "[=]", "z")
    for r in (3, 6):                         # two forward guns
        put_(r, 21, "======>", "z")
    for r in (4, 5):                         # tan stripes on the neck
        put_(r, 20, "|", "y")
        put_(r, 22, "|", "y")
    for r in (4, 5):                         # yellow cockpit nose
        put_(r, 23, "[:#:)", "Y")
        put_(r, 25, "#", "z")                # dark window
    return ["".join(r) for r in ch], ["".join(r) for r in co]


_RAZOR_LINES, _RAZOR_MASK = build_razor()
RAZOR = Art([_RAZOR_LINES], [_RAZOR_MASK])

_MANDO_TOP = [
    "  .---.  ",
    " /#####\\ ",
    " |  #  | ",
    " '._#_.' ",
    "/|[###]|\\",
    "| |[#]| |",
    "| |=#=| |",
    "  |___|  ",
]
_MANDO_A = _MANDO_TOP + ["  || ||  ", " _|| ||_ "]
_MANDO_B = _MANDO_TOP + ["  |/ \\|  ", " _/   \\_ "]
MANDO = Art([_MANDO_A, _MANDO_B], [paint(f, [
    (0, 3, 1, 7, "W"),                           # beskar helmet
    (1, 1, 2, 6, "z"), (2, 3, 4, 4, "z"),       # the T-shaped visor
    (4, 5, 0, 8, "W"),                           # pauldrons + chest plate
    (6, 6, 2, 6, "y"),                           # belt
    (7, 9, 2, 6, "z"),                           # legs, boots
]) for f in (_MANDO_A, _MANDO_B)])

_GROGU_A = ["-(o.o)-", " /===\\ ", " |_o_| ", "  d b  "]
_GROGU_B = ["-(o.o)-", " /===\\ ", " |_o_| ", "   db  "]
GROGU = Art([_GROGU_A, _GROGU_B], [paint(f, [
    (0, 0, 0, 6, "g"),                           # head + big ears
    (1, 2, 1, 5, "y"),                           # tan robe
    (2, 2, 3, 3, "W"),                           # the Mandalorian pendant
    (3, 3, 2, 4, "g"),
]) for f in (_GROGU_A, _GROGU_B)])

_VADER_TOP = [
    "  _.-|-._  ",
    " /=======\\ ",
    "/(###|###)\\",
    "|  \\|||/  |",
    " \\o_'-'_o/ ",
    " /|[.:']|\\ ",
    " |_|=#=|_| ",
    " | |___| | ",
]
_VADER_A = _VADER_TOP + ["  /|   |\\  ", " / ||_|| \\ ", "/_ ||_|| _\\"]
_VADER_B = _VADER_TOP + ["  /|   |\\  ", " / |/ \\| \\ ", "/_ /   \\ _\\"]
# arm + hilt, then a straight red blade in three poses: diagonal up, straight
# out, diagonal down (the blade never bends - each pose is one straight line)
_ARM = [(6, 10, "="), (6, 11, "#")]
_BLADE_UP = [(5, 12, "/"), (4, 13, "/"), (3, 14, "/"), (2, 15, "/")]
_BLADE_OUT = [(6, c, "-") for c in range(12, 19)]
_BLADE_DOWN = [(7, 12, "\\"), (8, 13, "\\"), (9, 14, "\\"), (10, 15, "\\")]


def _vader_frame(base, extra):
    rows = [list(r.ljust(19)) for r in base]
    for r, c, ch in _ARM + extra:
        rows[r][c] = ch
    return ["".join(r) for r in rows]


# played up -> out -> down -> out, with the legs stepping every frame
_VADER_FRAMES = [_vader_frame(_VADER_A, _BLADE_UP),
                 _vader_frame(_VADER_B, _BLADE_OUT),
                 _vader_frame(_VADER_A, _BLADE_DOWN),
                 _vader_frame(_VADER_B, _BLADE_OUT)]
VADER = Art(_VADER_FRAMES, [paint(f, [
    (0, 4, 0, 10, "Z"),                          # helmet shell
    (2, 2, 2, 4, "z"), (2, 2, 6, 8, "z"),       # big dark lenses
    (3, 3, 4, 6, "W"),                           # mouth-grille bars
    (4, 4, 2, 2, "W"), (4, 4, 8, 8, "W"),       # breathing-tube ends
    (5, 5, 3, 7, "Z"),                           # chest box
    (5, 5, 4, 4, "g"), (5, 5, 6, 6, "r"),       # control lights
    (6, 6, 11, 11, "W"),                         # saber hilt
    (0, 10, 12, 18, "R"),                        # red blade
]) for f in _VADER_FRAMES])

_JEDI = [
    (["   |   ", " o |   ", "/|\\|   ", "/ \\    "],
     ["   s   ", "   s   ", "   s   ", "       "]),
    (["     / ", " o  /  ", "/|\\/   ", "/ \\    "],
     ["     s ", "    s  ", "   s   ", "       "]),
    (["       ", " o     ", "/|\\----", "/ \\    "],
     ["       ", "       ", "   ssss", "       "]),
    (["       ", " o     ", "/|\\\\   ", "/ \\ \\  "],
     ["       ", "       ", "   s   ", "    s  "]),
]
_SWING = [0, 1, 2, 3, 2, 1]
JEDI = Art([_JEDI[i][0] for i in _SWING], [_JEDI[i][1] for i in _SWING])

# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


def init_colors():
    pairs = {}
    if not curses.has_colors():
        return pairs
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    base = [("r", curses.COLOR_RED), ("g", curses.COLOR_GREEN),
            ("y", curses.COLOR_YELLOW), ("b", curses.COLOR_BLUE),
            ("m", curses.COLOR_MAGENTA), ("c", curses.COLOR_CYAN),
            ("w", curses.COLOR_WHITE)]
    for i, (k, c) in enumerate(base, 1):
        curses.init_pair(i, c, bg)
        pairs[k] = curses.color_pair(i)
        pairs[k.upper()] = curses.color_pair(i) | curses.A_BOLD
    # real orange when the terminal has 256 colours, else fall back to yellow
    if curses.COLORS >= 256:
        curses.init_pair(len(base) + 1, 208, bg)
        pairs["o"] = curses.color_pair(len(base) + 1)
        pairs["O"] = pairs["o"] | curses.A_BOLD
        curses.init_pair(len(base) + 2, 245, bg)      # hull grey
        curses.init_pair(len(base) + 3, 252, bg)      # light grey detail
        curses.init_pair(len(base) + 4, 39, bg)       # bright blue engine glow
        pairs["z"] = curses.color_pair(len(base) + 2)
        pairs["Z"] = curses.color_pair(len(base) + 3)
        pairs["e"] = curses.color_pair(len(base) + 4)
        pairs["E"] = pairs["e"] | curses.A_BOLD
    else:
        pairs["e"], pairs["E"] = pairs["c"], pairs["C"]
        pairs["o"], pairs["O"] = pairs["y"], pairs["Y"]
        pairs["z"], pairs["Z"] = pairs["w"], pairs["W"]
    return pairs


class Entity:
    def __init__(self, art_, x, y, depth, direction=1, color="w", vx=0.0,
                 vy=0.0, anim=0.0, phase=0.0, die_off=True, ttl=None,
                 tag=None, target=None, on_death=None, cb=None, saber="G"):
        self.art, self.x, self.y = art_, float(x), float(y)
        self.depth, self.dir, self.color = depth, direction, color
        self.vx, self.vy, self.anim, self.fcount = vx, vy, anim, phase
        self.die_off, self.ttl = die_off, ttl
        self.tag, self.target = tag, target
        self.on_death, self.cb, self.saber = on_death, cb, saber
        self.alive = True

    # integer bounding box
    def box(self):
        x, y = int(math.floor(self.x)), int(math.floor(self.y))
        return x, y, x + self.art.w, y + self.art.h

    def die(self, world):
        if self.alive:
            self.alive = False
            world.dead.append(self)

    def update(self, world):
        if not self.alive:
            return
        self.x += self.vx
        self.y += self.vy
        self.fcount += self.anim
        if self.ttl is not None:
            self.ttl -= 1
            if self.ttl <= 0:
                self.die(world)
                return
        if self.cb:
            self.cb(self, world)
        if self.die_off:
            if ((self.vx > 0 and self.x >= world.W) or
                    (self.vx < 0 and self.x + self.art.w <= 0) or
                    (self.vy > 0 and self.y >= world.H) or
                    (self.vy < 0 and self.y + self.art.h <= 0)):
                self.die(world)

    def draw(self, scr, pairs, H, W):
        spr = self.art.sprites[self.dir][int(self.fcount) % self.art.n]
        x0, y0 = int(math.floor(self.x)), int(math.floor(self.y))
        for r, line in enumerate(spr.lines):
            y = y0 + r
            if y < 0 or y >= H:
                continue
            for c, ch in enumerate(line):
                if ch == " ":
                    continue
                x = x0 + c
                if x < 0 or x >= W:
                    continue
                key = self.color
                if spr.mask:
                    m = spr.mask[r][c]
                    if m == "s":
                        key = self.saber
                    elif m != " ":
                        key = m
                if ch == "?":
                    ch = " "
                try:
                    scr.addch(y, x, ch, pairs.get(key, 0))
                except curses.error:
                    pass


class Effect:
    """Base for things that are drawn but are not sprite entities."""
    depth = 10
    tag = None
    target = None
    on_death = None

    def __init__(self):
        self.alive = True

    def box(self):
        return (0, 0, 0, 0)

    def die(self, world):
        if self.alive:
            self.alive = False
            world.dead.append(self)

    def update(self, world):
        pass

    def draw(self, scr, pairs, H, W):
        pass


def put(scr, pairs, H, W, x, y, ch, key):
    if 0 <= x < W and 0 <= y < H:
        try:
            scr.addch(y, x, ch, pairs.get(key, 0))
        except curses.error:
            pass


class Particle(Effect):
    """A single spark / piece of debris."""

    def __init__(self, x, y, vx, vy, ch, color, ttl, grav=0.0):
        super().__init__()
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ch, self.color, self.ttl0, self.ttl = ch, color, ttl, ttl
        self.grav = grav
        self.depth = 12

    def update(self, world):
        self.x += self.vx
        self.y += self.vy
        self.vy = (self.vy + self.grav) * 0.96
        self.vx *= 0.96
        self.ttl -= 1
        if (self.ttl <= 0 or self.x < 0 or self.x >= world.W or
                self.y < 0 or self.y >= world.H):
            self.die(world)

    def draw(self, scr, pairs, H, W):
        ch = self.ch if self.ttl > self.ttl0 * 0.3 else "."
        put(scr, pairs, H, W, int(self.x), int(self.y), ch, self.color)


def spawn_burst(world, x, y, n, chars, colors, speed=1.0, ttl=(14, 30),
                grav=0.0):
    live = sum(1 for e in world.ents + world.new if isinstance(e, Particle))
    for _ in range(max(0, min(n, MAX_PARTICLES - live))):
        world.add(Particle(x, y,
                           random.uniform(-1, 1) * speed * 1.8,
                           random.uniform(-1, 1) * speed * 0.9,
                           random.choice(chars), random.choice(colors),
                           random.randint(*ttl), grav))


def line_cells(x0, y0, x1, y1):
    cells = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        cells.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return cells


class SuperLaser(Effect):
    """Death Star superlaser: charge, fire, impact on the horizon, fade."""
    CHARGE, GROW, HOLD, FADE = 50, 14, 28, 10

    def __init__(self, world):
        super().__init__()
        self.tag = "superlaser"
        self.depth = 5
        self.cx, self.cy = world.ds
        self.tx = random.randint(int(world.W * 0.55), world.W - 3)
        self.ty = world.horizon - 1
        self.cells = line_cells(self.cx, self.cy, self.tx, self.ty)
        self.t = 0

    def _range(self):
        ft = self.t - self.CHARGE
        n = len(self.cells)
        if ft <= 0:
            return 0, 0
        if ft < self.GROW:
            return 0, max(1, n * ft // self.GROW)
        if ft <= self.GROW + self.HOLD:
            return 0, n
        return n * (ft - self.GROW - self.HOLD) // self.FADE, n

    def update(self, world):
        self.t += 1
        a, b = self._range()
        ft = self.t - self.CHARGE
        if b > a:
            beam = self.cells[a:b]
            for e in world.ents:
                if not (e.alive and e.tag in ("fighter", "tie")):
                    continue
                x0, y0, x1, y1 = e.box()
                if any(x0 <= x < x1 and y0 <= y < y1 for x, y in beam):
                    explode(world, e)
                    e.die(world)
        if self.GROW <= ft <= self.GROW + self.HOLD and ft % 3 == 0:
            ex = self.tx + random.randint(-6, 6) - EXPLOSION.w // 2
            ey = self.ty + random.randint(-3, 1) - EXPLOSION.h // 2
            world.add(Entity(EXPLOSION, ex, ey, 6, 1, color=random.choice("YRG"),
                             anim=0.35, ttl=int(EXPLOSION.n / 0.35) + 1,
                             die_off=False))
            spawn_burst(world, self.tx, self.ty, 6, "*#%.'", "GYy",
                        speed=1.4, ttl=(10, 24))
        if self.t >= self.CHARGE + self.GROW + self.HOLD + self.FADE:
            self.die(world)

    def draw(self, scr, pairs, H, W):
        cx, cy = self.cx, self.cy
        if self.t <= self.CHARGE:
            prog = self.t / float(self.CHARGE)
            r = 9 * (1 - prog)
            for i in range(6):
                ang = i * math.pi / 3 + self.t * 0.25
                put(scr, pairs, H, W, cx + int(round(math.cos(ang) * r * 2)),
                    cy + int(round(math.sin(ang) * r)), "*", "G")
            put(scr, pairs, H, W, cx, cy, ".oO@"[min(3, int(prog * 4))], "G")
            return
        a, b = self._range()
        for x, y in self.cells[a:b]:
            put(scr, pairs, H, W, x, y, random.choice("#=*"), "G")
            put(scr, pairs, H, W, x, y - 1, random.choice(".:"), "g")
            put(scr, pairs, H, W, x, y + 1, random.choice(".:"), "g")
        put(scr, pairs, H, W, cx, cy, "@", "G")


def solid_at(e, x, y):
    spr = e.art.sprites[e.dir][int(e.fcount) % e.art.n]
    c, r = x - int(math.floor(e.x)), y - int(math.floor(e.y))
    return 0 <= r < spr.h and 0 <= c < spr.w and spr.lines[r][c] != " "


def ships_touch(a, b, W):
    """True when solid cells of two on-screen sprites overlap."""
    ax0, ay0, ax1, ay1 = a.box()
    bx0, by0, bx1, by1 = b.box()
    x0, x1 = max(ax0, bx0, 0), min(ax1, bx1, W)
    y0, y1 = max(ay0, by0), min(ay1, by1)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if solid_at(a, x, y) and solid_at(b, x, y):
                return True
    return False


TORPEDO = Art([["=o>"], ["=O>"]])


class DeathStarRun(Effect):
    """Rare scene: an X-wing torpedoes the Death Star, it blows up, and the
    screen jumps to hyperspace into a fresh scene with a new Death Star."""

    def __init__(self, world):
        super().__init__()
        self.tag, self.depth = "attack", 3
        self.state, self.t, self.hits, self.fired = "approach", 0, 0, 0
        x0, y0, x1, y1 = world.ds_box
        self.impact_x = x1 - 3
        cy = int(world.ds_center[1])
        # the hero X-wing comes in from the right on the Death Star's centre row
        self.hero = world.add(Entity(XWING, world.W, cy - XWING.h // 2, 28, -1,
                                     "W", vx=-1.0, tag="hero"))

        def cb(e, w):
            if on_screen(e, w) and random.random() < 0.04:
                fire(w, e, "G", harmless=True)

        for i, off in enumerate((-3, 3)):       # two TIEs on its tail
            world.add(Entity(TIE, world.W + XWING.w + 8 + 10 * i,
                             cy - TIE.h // 2 + off, 30, -1, "w", vx=-1.0,
                             tag="fighter", cb=cb))

    def fire_torpedo(self, world):
        self.fired += 1
        h = self.hero
        world.add(Entity(TORPEDO, h.x - TORPEDO.w, h.y + h.art.h // 2, 24, -1,
                         "O", vx=-1.6, anim=0.4, tag="torpedo",
                         cb=self._torp, on_death=self._torp_done))

    def _torp(self, e, world):
        if e.x <= self.impact_x:                 # hit the surface
            world.add(Entity(EXPLOSION, e.x - 2, e.y - 2, 8, 1, color="Y",
                             anim=0.35, ttl=int(EXPLOSION.n / 0.35) + 1,
                             die_off=False))
            spawn_burst(world, e.x, e.y, 9, "*#%.'", "YRWy", speed=1.1,
                        ttl=(10, 24))
            e.die(world)

    def _torp_done(self, e, world):
        self.hits += 1

    def update(self, world):
        self.t += 1
        if self.state == "approach":
            if not self.hero.alive:
                self.die(world)
            elif self.hero.x <= self.impact_x + 30:
                self.state, self.t = "torp", 0
                self.hero.vx = -0.7
        elif self.state == "torp":
            if self.t % 14 == 1 and self.fired < 3:
                self.fire_torpedo(world)
                if self.fired == 3:              # then peel away upwards
                    self.hero.vx, self.hero.vy = -0.6, -0.35
            if self.hits >= 3 or self.t > 200:
                self.state, self.t = "boom", 0
        else:
            self.boom(world)

    def boom(self, world):
        cx, cy = world.ds_center
        rx, ry = world.ds_rad
        p = min(1.0, self.t / 55.0)
        live = sum(1 for e in world.ents + world.new if isinstance(e, Particle))
        keep = []
        for cell in world.ds_cells:              # the shell blows apart
            y, x, ch, col = cell
            nd = math.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
            if nd + random.random() * 0.18 <= p * 1.25:
                if ch != " " and random.random() < 0.45 and live < MAX_PARTICLES + 150:
                    live += 1
                    world.add(Particle(
                        x, y, (x - cx) / rx * 1.4 + random.uniform(-0.4, 0.4),
                        (y - cy) / ry * 0.7 + random.uniform(-0.3, 0.3),
                        ch if random.random() < 0.6 else random.choice("*+x"),
                        random.choice("wWyYr"), random.randint(14, 30)))
            else:
                keep.append(cell)
        world.ds_cells = keep
        if self.t % 2 == 0:                      # fireballs across the sphere
            a, r = random.uniform(0, 2 * math.pi), math.sqrt(random.random())
            px = cx + math.cos(a) * r * rx * p
            py = cy + math.sin(a) * r * ry * p
            world.add(Entity(EXPLOSION, px - 2, py - 2, 6, 1,
                             color=random.choice("YRYW"), anim=0.35,
                             ttl=int(EXPLOSION.n / 0.35) + 1, die_off=False))
        if self.t % 5 == 0:
            spawn_burst(world, cx, cy, 10, "*#%@+", "YRyW", speed=1.5 + p,
                        ttl=(14, 34))
        if self.t >= 65:                         # gone: jump to hyperspace
            world.ds_cells, world.ds, world.ds_center = [], None, None
            world.add(HyperJump(world))
            self.die(world)


class HyperJump(Effect):
    """Screen-wide jump to hyperspace: streaks ramp up, the scene is hidden,
    a flash swaps in a brand new scene, and the streaks fade away."""
    RAMP, BLANK, FLASH, FADE = 25, 35, 3, 30

    def __init__(self, world):
        super().__init__()
        self.tag, self.depth, self.t = "hyper", 0, 0
        self.rays = [(random.uniform(0, 2 * math.pi), random.random(),
                      random.uniform(0.012, 0.035)) for _ in range(170)]

    def hides_scene(self):
        return self.RAMP <= self.t < self.RAMP + self.BLANK + self.FLASH

    def update(self, world):
        self.t += 1
        if self.t == self.RAMP + self.BLANK:     # on the flash: new scene
            world.pending_reset = True
        if self.t >= self.RAMP + self.BLANK + self.FLASH + self.FADE:
            self.die(world)

    def draw(self, scr, pairs, H, W):
        t, on = self.t, self.RAMP + self.BLANK
        if on <= t < on + self.FLASH:            # white-out
            for y in range(H):
                try:
                    scr.addstr(y, 0, "#" * (W - 1), pairs.get("W", 0))
                except curses.error:
                    pass
            return
        if t < self.RAMP:
            f = t / float(self.RAMP)
            length, n = 1 + 16 * f * f, int(len(self.rays) * f)
        elif t < on:
            length, n = 18 + (t - self.RAMP) * 0.3, len(self.rays)
        else:
            f = (t - on - self.FLASH) / float(self.FADE)
            length, n = max(1.0, 18 * (1 - f)), int(len(self.rays) * (1 - f))
        cx, cy = W / 2.0, H / 2.0
        R = math.hypot(cx, cy * 2)
        for ang, phase, spd in self.rays[:max(0, n)]:
            head = ((phase + spd * t * 3) % 1.0) * R
            ca, sa = math.cos(ang), math.sin(ang)
            ch = ("-" if abs(sa) < 0.38 else "|" if abs(ca) < 0.38 else
                  "\\" if ca * sa > 0 else "/")
            for k in range(int(length)):
                rr = head - k
                if rr < 3:
                    break
                put(scr, pairs, H, W, int(cx + ca * rr), int(cy + sa * rr / 2.0),
                    ch, "W" if k < 2 else ("C" if k < length * 0.6 else "c"))


class World:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.horizon = H - max(5, int(round(H * GROUND_FRAC)))
        self.pending_reset = False
        self._setup()

    def _setup(self):
        """(Re)build the whole scene: sky, ground, a fresh Death Star, events."""
        self.ents, self.new, self.dead = [], [], []
        self.bg = []          # static cells: (y, x, ch, colour key)
        self.ds_cells = []    # the Death Star's cells (so it can blow up)
        self.stars = []
        self.ds = None        # screen position of the Death Star's dish
        self.ds_center = self.ds_rad = self.ds_box = None
        self.sl_cool = 300    # frames before the superlaser may fire
        self.age = 0
        self.last_sky = None  # last big sky event (no two destroyers in a row)
        self.last_ground = None  # last big ground event (never repeated)
        self.atst_cool = 0    # frames before another AT-ST may appear
        self._build_background()
        for _ in range(max(2, self.W // 30)):
            float_debris(self, anywhere=True)
        random_object(None, self)

    # ---- background ----------------------------------------------------
    def _stamp(self, art_, x, y, color, out=None):
        out = self.bg if out is None else out
        spr = art_.sprites[1][0]
        for r, line in enumerate(spr.lines):
            for c, ch in enumerate(line):
                if ch == " ":
                    continue
                if 0 <= y + r < self.H and 0 <= x + c < self.W:
                    m = spr.mask[r][c] if spr.mask else " "
                    out.append((y + r, x + c, " " if ch == "?" else ch,
                                color if m == " " else m))

    def _build_background(self):
        W, H, hz = self.W, self.H, self.horizon
        # stars (upper sky, clear of the ridge)
        n = max(10, W * max(1, hz - 3) // 18)
        for _ in range(n):
            self.stars.append([random.uniform(0, W),
                               random.randint(0, max(0, hz - 3)),
                               random.uniform(0.01, 0.12),
                               random.choice(".....+*'"),
                               random.choice("wwwwwyc")])
        # Death Star: scales with the sky, sized to fit above the ridge
        ry = min(12, int(hz * 0.28), (hz - 5) // 2)
        if ry >= 4:
            rx = 2 * ry + 1
            lines, dmask, dcol, drow = build_death_star(
                rx, ry, random.randint(0, 10 ** 6))
            star = Art([lines], [dmask])
            x = max(1, min(int(W * random.uniform(0.08, 0.2)), W - star.w - 1))
            self._stamp(star, x, 1, "w", self.ds_cells)
            self.ds = (x + dcol, 1 + drow)
            self.ds_center = (x + rx, 1 + ry)
            self.ds_rad = (rx + 0.5, ry + 0.5)
            self.ds_box = (x, 1, x + star.w, 1 + star.h)
        # dune ridge
        ph = random.uniform(0, 6)
        prev = None
        for x in range(W):
            p = int(round(1 + math.sin(x / 9.0 + ph) +
                          0.7 * math.sin(x / 4.0 + 2 * ph)))
            p = max(0, min(2, p))
            ch = "_"
            if prev is not None:
                ch = "/" if p > prev else "\\" if p < prev else "_"
            prev = p
            self.bg.append((hz - p, x, ch, "y"))
        # sandy speckles on the ground
        for _ in range(W * (H - hz) // 14):
            self.bg.append((random.randint(hz + 1, H - 1),
                            random.randint(0, W - 1),
                            random.choice(".,:`'"), "y"))
        # a few rocks
        for _ in range(max(2, W // 25)):
            x = random.randint(1, W - 6)
            y = random.randint(hz + 2, H - 1)
            for i, ch in enumerate("(_)" if random.random() < .5 else ".o."):
                self.bg.append((y, x + i, ch, "y"))

    # ---- simulation ----------------------------------------------------
    def add(self, e):
        self.new.append(e)
        return e

    def count(self, tag):
        return sum(1 for e in self.ents + self.new if e.alive and e.tag == tag)

    def tick(self):
        self.ents += self.new
        self.new = []
        for e in self.ents:
            e.update(self)
        # collisions: bolts vs their target tag
        for b in self.ents:
            if not (b.alive and b.target):
                continue
            bx0, by0, bx1, by1 = b.box()
            for t in self.ents:
                hit = (t.tag in b.target if isinstance(b.target, tuple)
                       else t.tag == b.target)
                if not (t.alive and hit):
                    continue
                tx0, ty0, tx1, ty1 = t.box()
                if bx0 < tx1 and tx0 < bx1 and by0 < ty1 and ty0 < by1:
                    explode(self, t)
                    t.die(self)
                    b.die(self)
                    break
        # fighters that collide explode together
        ships = [e for e in self.ents if e.alive and e.tag in ("tie", "fighter")]
        for i, a in enumerate(ships):
            for b in ships[i + 1:]:
                if a.alive and b.alive and ships_touch(a, b, self.W):
                    explode(self, a)
                    explode(self, b)
                    a.die(self)
                    b.die(self)
        dead, self.dead = self.dead, []
        self.ents = [e for e in self.ents if e.alive]
        for e in dead:
            if e.on_death:
                e.on_death(e, self)
        # parallax stars + twinkle
        for s in self.stars:
            s[0] -= s[2]
            if s[0] < 0:
                s[0] += self.W
            if random.random() < 0.004:
                s[3] = random.choice(".+*'")
        self.ambient()
        if self.pending_reset:                   # hyperspace jump: new scene
            self.pending_reset = False
            keep = [e for e in self.ents if isinstance(e, HyperJump) and e.alive]
            self._setup()
            self.ents += keep

    def ambient(self):
        self.age += 1
        if self.atst_cool > 0:
            self.atst_cool -= 1
        if (self.count("fighter") < 2 + self.W // 40 and
                not self.count("attack") and random.random() < 0.025):
            dogfight(self)
        if (self.count("ground") < 2 + self.W // 60 and
                random.random() < 0.02):
            spawn_ground(self)
        if (self.count("debris") < 2 + self.W // 25 and
                random.random() < 0.03):
            float_debris(self)
        if self.sl_cool > 0:
            self.sl_cool -= 1
        elif self.ds and random.random() < 0.002:
            self.fire_superlaser()
        if self.age > 1800 and random.random() < 0.00012:   # very rare
            self.start_attack()

    def start_attack(self):
        """An X-wing torpedoes the Death Star (needs one on screen)."""
        if (self.ds and not self.count("attack") and not self.count("hyper")
                and not self.count("superlaser")):
            self.add(DeathStarRun(self))

    def fire_superlaser(self):
        if (self.ds and self.count("superlaser") == 0 and
                not self.count("attack") and not self.count("hyper")):
            self.add(SuperLaser(self))
            self.sl_cool = 900

    def draw(self, scr, pairs):
        H, W = self.H, self.W
        hj = next((e for e in self.ents if isinstance(e, HyperJump)), None)
        if hj is not None and hj.hides_scene():
            hj.draw(scr, pairs, H, W)
            return
        for x, y, _, ch, col in [(s[0], s[1], 0, s[3], s[4]) for s in self.stars]:
            try:
                scr.addch(int(y), int(x), ch, pairs.get(col, 0))
            except curses.error:
                pass
        for y, x, ch, col in self.bg + self.ds_cells:
            try:
                scr.addch(y, x, ch, pairs.get(col, 0))
            except curses.error:
                pass
        for e in sorted(self.ents, key=lambda e: -e.depth):
            e.draw(scr, pairs, H, W)


# --------------------------------------------------------------------------
# Helpers & actors
# --------------------------------------------------------------------------

def entry_x(world, art_, d):
    return -art_.w if d > 0 else world.W


def sky_y(world, h):
    return random.randint(1, max(1, world.horizon - h - 2))


def ground_row(world, h):
    lo = min(world.horizon + 3, world.H - 1)
    base = random.randint(lo, world.H - 1)
    return base, base - h + 1


def explode(world, target):
    x0, y0, x1, y1 = target.box()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    world.add(Entity(EXPLOSION, cx - EXPLOSION.w / 2.0, cy - EXPLOSION.h / 2.0,
                     10, 1, color=random.choice("YRY"), anim=0.35,
                     ttl=int(EXPLOSION.n / 0.35) + 1, die_off=False))
    spawn_burst(world, cx, cy, random.randint(5, 9), "-=/\\|%#*.", "wwyr",
                speed=0.9, ttl=(14, 32),
                grav=0.05 if cy >= world.horizon else 0.0)


def spark_bolt(b, world):
    """A blaster bolt that fizzles out in a little shower of sparks."""
    x = b.x + (b.art.w if b.dir > 0 else 0)
    spawn_burst(world, x, b.y, 5, ".*'`", "YyW", speed=0.6, ttl=(5, 10))


def fire(world, shooter, color, harmless, dy=0, speed=2.0, ttl=None,
         on_death=None):
    d = shooter.dir
    x = shooter.x + shooter.art.w if d > 0 else shooter.x - BOLT.w
    y = shooter.y + shooter.art.h // 2 + dy
    world.add(Entity(BOLT, x, y, 20, d, color=color, vx=d * speed,
                     tag="bolt", target=None if harmless else "tie",
                     ttl=ttl, on_death=on_death))


def on_screen(e, world):
    return e.x >= 0 and e.x + e.art.w <= world.W


XWING_BARRELS = (0, 6)       # cannon rows (top and bottom wing barrels)
XWING_MUZZLE = 12            # column just past the cannon tips


def fire_xwing(world, shooter, target=None):
    """Red bolts from the top and bottom barrels, converging on the target."""
    d = shooter.dir
    for row in XWING_BARRELS:
        x = (shooter.x + XWING_MUZZLE if d > 0 else
             shooter.x + shooter.art.w - XWING_MUZZLE - BOLT.w)
        y = shooter.y + row
        vx, vy = d * 2.0, 0.0
        if target is not None and target.alive:
            tx = target.x + target.art.w / 2.0
            ty = target.y + target.art.h // 2
            closing = max(0.5, abs(vx - target.vx))
            vy = (ty - y) / max(1.0, abs(tx - x) / closing)
        world.add(Entity(BOLT, x, y, 20, d, color="R", vx=vx, vy=vy,
                         tag="bolt", target="tie"))


def fire_rebel(world, shooter, target):
    if shooter.art is XWING:
        fire_xwing(world, shooter, target)
    else:                                    # Y-wing: blue bolt from the nose
        fire(world, shooter, "B", harmless=False)


REBELS = [(XWING, "W", 0.0), (XWING, "W", 0.0), (YWING, "y", -0.06)]


def dogfight(world):
    """Either a rebel fighter chases (and shoots down) a TIE, or a TIE
    chases a rebel fighter and misses."""
    d = random.choice((1, -1))
    # shared centre row; keep clear of fighters that are already flying
    busy = [e.y + e.art.h / 2.0 for e in world.ents + world.new
            if e.alive and e.tag in ("tie", "fighter")]
    for _ in range(8):
        cy = sky_y(world, XWING.h) + XWING.h // 2
        if all(abs(cy - b) >= 6 for b in busy):
            break
    else:
        return                                 # sky too crowded, skip this one
    speed = random.uniform(0.5, 0.8)
    gap = random.randint(8, 16)                # clear space between the two
    rart, rcol, rspd = random.choice(REBELS)
    rebel_chases = random.random() < 0.6
    lead_art, chase_art = (TIE, rart) if rebel_chases else (rart, TIE)
    x_lead = entry_x(world, lead_art, d)
    # the chaser starts completely behind the leader's tail
    x_chase = (x_lead - chase_art.w - gap if d > 0
               else x_lead + lead_art.w + gap)
    if rebel_chases:
        lead = Entity(TIE, x_lead, cy - TIE.h // 2, 30, d, "w", vx=d * speed,
                      tag="tie")

        def cb(e, w):
            if (on_screen(e, w) and lead.alive and on_screen(lead, w) and
                    random.random() < 0.07):
                fire_rebel(w, e, lead)

        chaser = Entity(rart, x_chase, cy - rart.h // 2, 30, d, rcol,
                        vx=d * (speed + 0.07 + rspd), tag="fighter", cb=cb)
    else:
        lead = Entity(rart, x_lead, cy - rart.h // 2, 30, d, rcol, vx=d * speed,
                      tag="fighter")

        def cb(e, w):
            if on_screen(e, w) and random.random() < 0.05:
                fire(w, e, "G", harmless=True,
                     dy=random.choice((-1, 1)) * (lead.art.h // 2 + 1))

        # no faster than the leader: the TIE chases but never rams it
        chaser = Entity(TIE, x_chase, cy - TIE.h // 2, 30, d, "w",
                        vx=d * (speed + 0.02), tag="fighter", cb=cb)
    world.add(lead)
    world.add(chaser)


def float_debris(world, anywhere=False):
    """Slowly drifting wreckage from earlier battles."""
    art_ = random.choice((DEBRIS_SPIN, DEBRIS_CHUNK))
    d = random.choice((1, -1))
    x = (random.uniform(0, world.W) if anywhere else entry_x(world, art_, d))
    world.add(Entity(art_, x, random.randint(0, max(0, world.horizon - 3)),
                     60, d, "w", vx=d * random.uniform(0.04, 0.15),
                     vy=random.uniform(-0.02, 0.02),
                     anim=random.uniform(0.05, 0.2), tag="debris"))


# -- big events (chained through death callbacks, like asciiquarium) ---------

BOLT_V = Art([["|"]])
BOLT_BACK = Art([["\\"]])
BOLT_FWD = Art([["/"]])
SD_TARGETS = ("tie", "fighter", "freighter")      # what the turrets can hit


def sd_guns(e, w):
    """Star Destroyer turrets: green bolts, led at the nearest ship, that can
    destroy any ship they hit."""
    e.cool = getattr(e, "cool", 0) - 1
    if e.cool > 0:
        return
    spots = []
    for r, c in e.art.turrets:
        col = c if e.dir > 0 else e.art.w - 1 - c
        x, y = int(math.floor(e.x)) + col, int(math.floor(e.y)) + r
        if 0 <= x < w.W and 0 <= y < w.H:
            spots.append((x, y))
    ships = [t for t in w.ents if t.alive and t.tag in SD_TARGETS
             and on_screen(t, w)]
    if not spots or not ships:
        return
    sx, sy = random.choice(spots)

    def centre(t):
        return t.x + t.art.w / 2.0, t.y + t.art.h / 2.0

    tgt = min(ships, key=lambda t: abs(centre(t)[0] - sx) +
              2 * abs(centre(t)[1] - sy))
    speed = 1.8
    tx, ty = centre(tgt)
    for _ in range(2):                       # aim where it will be
        dist = max(1.0, math.hypot(tx - sx, (ty - sy) * 2))
        t_hit = dist / speed
        tx, ty = centre(tgt)[0] + tgt.vx * t_hit, centre(tgt)[1] + tgt.vy * t_hit
    tx += random.uniform(-4.0, 4.0)          # the gunners aren't perfect
    ty += random.uniform(-1.5, 1.5)
    dx, dy2 = tx - sx, (ty - sy) * 2
    dist = max(1.0, math.hypot(dx, dy2))
    if dist > w.W * 0.6:
        return
    vx, vy = dx / dist * speed, dy2 / dist * speed / 2.0
    if abs(vy * 2) < 0.35 * abs(vx):
        bolt = BOLT
    elif abs(vx) < 0.35 * abs(vy * 2):
        bolt = BOLT_V
    else:
        bolt = BOLT_BACK if vx * vy > 0 else BOLT_FWD
    w.add(Entity(bolt, sx, sy, 18, 1, color="G", vx=vx, vy=vy, tag="bolt",
                 target=SD_TARGETS, ttl=90))
    spawn_burst(w, sx, sy, 3, "*+.", "Gg", speed=0.4, ttl=(3, 6))
    e.cool = random.randint(30, 60)


def ev_star_destroyer(world):
    d = random.choice((1, -1))
    half = max(3, min(12, int(world.horizon * 0.5) // 2))
    length = min(int(3.4 * (2 * half + 1)), int(world.W * 0.7))
    lines, mask, turrets = build_star_destroyer(half, length)
    sd = Art([lines], [mask])
    sd.turrets = turrets
    world.last_sky = "sd"
    speed = max(0.22, (world.W + sd.w) / (45 * 15.0))
    world.add(Entity(sd, entry_x(world, sd, d), sky_y(world, sd.h), 45, d, "z",
                     vx=d * speed, on_death=next_sky, cb=sd_guns))


def ev_razor(world, chain=True):
    """The Razor Crest crosses the sky, about the Falcon's size and speed."""
    d = random.choice((1, -1))
    if chain:
        world.last_sky = "razor"

    def cb(e, w):                            # now and then its guns go off
        if on_screen(e, w) and random.random() < 0.02:
            fire(w, e, "R", harmless=True, dy=random.choice((-2, 1)),
                 speed=1.8)

    world.add(Entity(RAZOR, entry_x(world, RAZOR, d), sky_y(world, RAZOR.h),
                     35, d, "z", vx=d * 1.0, cb=cb, tag="freighter",
                     on_death=next_sky if chain else None))


def ev_falcon(world, chain=True):
    d = random.choice((1, -1))
    if chain:
        world.last_sky = "falcon"
    fy = sky_y(world, FALCON.h)
    world.add(Entity(FALCON, entry_x(world, FALCON, d), fy, 35, d, "z",
                     vx=d * 1.0, tag="freighter",
                     on_death=next_sky if chain else None))
    for i, off in enumerate((-3, 0, 3)):
        ty = max(1, min(world.horizon - TIE.h - 1, fy + FALCON.h // 2 - 1 + off))
        xf = entry_x(world, FALCON, d)
        gap = 6 + 8 * i
        # trailing edge of the Falcon + gap, measured from its stern
        x = xf - TIE.w - gap if d > 0 else xf + FALCON.w + gap

        def cb(e, w):
            if on_screen(e, w) and random.random() < 0.04:
                fire(w, e, "G", harmless=True)

        world.add(Entity(TIE, x, ty, 33, d, "w", vx=d * 1.0,
                         tag="fighter", cb=cb))


def _spawn_atat(world):
    world.last_ground = "atat"
    d = random.choice((1, -1))
    base, y = ground_row(world, ATAT.h)

    def cb(e, w):
        if on_screen(e, w) and random.random() < 0.012:
            fire(w, e, "R", harmless=True, dy=-2)

    world.add(Entity(ATAT, entry_x(world, ATAT, d), y, 80 - base, d, "z",
                     vx=d * 0.25, anim=0.12, on_death=next_ground, cb=cb,
                     tag="atat"))


def ev_atat(world):
    _spawn_atat(world)


def ev_atst(world):
    """A lone AT-ST walks across the desert."""
    world.last_ground = "atst"
    d = random.choice((1, -1))
    ground_entity(world, ATST, "z", 0.3, 0.12, d, cb=atst_cb, tag="atst",
                  on_death=atst_event_done)


def ev_jedi_duel(world):
    world.last_ground = "duel"
    base, y = ground_row(world, JEDI.h)
    x0 = world.W // 2 - 8
    ttl = 150

    def clash(e, w):
        # a shower of sparks each time the sabers meet
        if int(e.fcount) % 6 in (2, 4) and (e.fcount % 1) < e.anim:
            spawn_burst(w, e.x + 7, e.y + 2, 4, ".*'", "YW", speed=0.5,
                        ttl=(5, 9))

    world.add(Entity(JEDI, x0, y, 80 - base, 1, "w", anim=0.25, die_off=False,
                     ttl=ttl, saber="B", on_death=next_ground, cb=clash))
    world.add(Entity(JEDI, x0 + 8, y, 80 - base, -1, "w", anim=0.25,
                     phase=3.0, die_off=False, ttl=ttl, saber="R"))


def ev_patrol(world):
    """Stormtroopers chase a pair of Ewoks across the desert."""
    world.last_ground = "patrol"
    d = random.choice((1, -1))
    _, base = ground_entity(world, EWOK, "y", 0.34, 0.2, d)
    ground_entity(world, EWOK, "y", 0.34, 0.2, d, base=base, x_back=7)
    for i in range(3):
        row = min(world.H - 1, base + (i % 2))
        ground_entity(world, TROOPER, "W", 0.28, 0.18, d, base=row,
                      x_back=18 + 8 * i, cb=trooper_cb,
                      on_death=next_ground if i == 2 else None)


# Two independent chains run side by side (like asciiquarium's random_object):
# one big event in the sky and one on the ground, each starting the next
# when it finishes.  The Falcon is weighted so it turns up regularly.
SKY_EVENTS = [ev_star_destroyer, ev_falcon, ev_falcon, ev_falcon, ev_razor,
              ev_razor]
SKY_NAMES = {ev_star_destroyer: "sd", ev_falcon: "falcon", ev_razor: "razor"}
GROUND_EVENTS = [ev_atat, ev_atst, ev_jedi_duel, ev_patrol]
EVENT_NAMES = {ev_atat: "atat", ev_atst: "atst", ev_jedi_duel: "duel",
               ev_patrol: "patrol"}


def next_sky(dead, world):
    # never the same big sky event twice in a row
    events = [e for e in SKY_EVENTS if SKY_NAMES[e] != world.last_sky]
    random.choice(events)(world)


def next_ground(dead, world):
    # never the same big ground event twice in a row
    events = [e for e in GROUND_EVENTS if EVENT_NAMES[e] != world.last_ground]
    if world.count("atst") or world.atst_cool > 0:   # AT-ST needs a breather,
        events = [e for e in events if e is not ev_atst]  # and never with...
    if world.count("atst"):                  # ...the AT-AT
        events = [e for e in events if e is not ev_atat]
    if world.count("droids"):                # nor with the droids
        events = [e for e in events if e is not ev_atst]
    random.choice(events)(world)


def random_object(dead, world):
    next_sky(dead, world)
    next_ground(dead, world)


# -- ground life ------------------------------------------------------------

def ground_entity(world, art_, color, speed, anim, d, base=None, x_back=0,
                  saber="G", cb=None, on_death=None, tag="ground"):
    """Add a walker standing on the ground; returns (entity, base_row)."""
    if base is None:
        base, _ = ground_row(world, art_.h)
    y = base - art_.h + 1
    x = entry_x(world, art_, d) - d * x_back
    e = world.add(Entity(art_, x, y, 80 - base, d, color, vx=d * speed,
                         anim=anim, saber=saber, cb=cb, on_death=on_death,
                         tag=tag))
    return e, base


def trooper_cb(e, w):
    if on_screen(e, w) and random.random() < 0.03:
        fire(w, e, "R", harmless=True, dy=-1, speed=1.5,
             ttl=random.randint(10, 22), on_death=spark_bolt)


GROUND_KINDS = ("speeder", "speeder", "atst", "droids", "droids", "jedi",
                "yoda", "ewok", "trooper", "trooper", "mando", "vader")


ATST_COOLDOWN = 1500         # ~100 s between AT-ST appearances


def atst_gone(e, world):
    """An AT-ST just left the screen: keep the next one away for a while."""
    world.atst_cool = ATST_COOLDOWN


def atst_event_done(e, world):
    atst_gone(e, world)
    next_ground(e, world)


def atst_cb(e, w):
    if on_screen(e, w) and random.random() < 0.02:
        fire(w, e, "R", harmless=True, dy=-3, speed=1.5,
             ttl=random.randint(10, 22), on_death=spark_bolt)


def spawn_ground(world):
    # one speeder / AT-ST / droid pair / Yoda at a time; no ambient AT-ST
    # while an AT-AT marches
    blocked = {k for k in ("speeder", "atst", "droids", "yoda", "mando",
                           "vader") if world.count(k)}
    if world.count("atat") or world.atst_cool > 0:
        blocked.add("atst")
    if world.count("atst"):                  # droids stay off the AT-ST's path
        blocked.add("droids")
    if world.count("droids"):
        blocked.add("atst")
    kind = random.choice([k for k in GROUND_KINDS if k not in blocked])
    d = random.choice((1, -1))
    if kind == "ewok":
        base = None
        for i in range(random.randint(1, 3)):
            _, base = ground_entity(world, EWOK, "y", 0.25, 0.2, d,
                                    base=base, x_back=7 * i)
    elif kind == "droids":                   # C-3PO and R2-D2 walk together
        _, base = ground_entity(world, C3PO, "Y", 0.32, 0.22, d, tag="droids")
        ground_entity(world, R2D2, "W", 0.32, 0.22, d, base=base,
                      x_back=C3PO.w + 3, tag="droids")
    elif kind == "trooper":
        ground_entity(world, TROOPER, "W", 0.22, 0.18, d, cb=trooper_cb)
    elif kind == "mando":                    # the Mandalorian and Grogu
        _, base = ground_entity(world, MANDO, "z", 0.28, 0.2, d, tag="mando")
        ground_entity(world, GROGU, "g", 0.28, 0.2, d, base=base,
                      x_back=MANDO.w + 2, tag="mando")
    elif kind == "vader":
        ground_entity(world, VADER, "z", 0.1, 0.08, d, tag="vader")   # as slow as Yoda
    elif kind == "yoda":
        ground_entity(world, YODA, "g", 0.1, 0.08, d, tag="yoda")
    elif kind == "atst":
        ground_entity(world, ATST, "z", 0.3, 0.12, d, cb=atst_cb, tag="atst",
                      on_death=atst_gone)
    elif kind == "speeder":
        ground_entity(world, SPEEDER, "o", 1.3, 0.0, d, tag="speeder")
    else:                                    # jedi
        ground_entity(world, JEDI, "w", 0.22, 0.18, d,
                      saber=random.choice("GBg"))


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------

def run(scr, fps):
    curses.curs_set(0)
    pairs = init_colors()
    dt = 1.0 / fps
    world, paused = None, False
    nxt = time.monotonic()
    while True:
        H, W = scr.getmaxyx()
        if world is None or (world.W, world.H) != (W, H):
            world = World(W, H) if (W >= MIN_W and H >= MIN_H) else None
        scr.erase()
        if world is None:
            msg = "Terminal too small (need %dx%d)" % (MIN_W, MIN_H)
            try:
                scr.addstr(0, 0, msg[:max(0, W - 1)])
            except curses.error:
                pass
        else:
            if not paused:
                world.tick()
            world.draw(scr, pairs)
        scr.refresh()

        nxt += dt
        while True:
            remaining = nxt - time.monotonic()
            if remaining <= 0:
                break
            scr.timeout(max(1, int(remaining * 1000)))
            k = scr.getch()
            if k in (ord("q"), ord("Q")):
                return
            if k in (ord("r"), ord("R")):
                world = None
                break
            if k in (ord("p"), ord("P")):
                paused = not paused
            if k in (ord("s"), ord("S")) and world:
                world.fire_superlaser()
            if k in (ord("f"), ord("F")) and world:
                ev_falcon(world, chain=False)
            if k in (ord("x"), ord("X")) and world:
                world.start_attack()
            if k in (ord("c"), ord("C")) and world:
                ev_razor(world, chain=False)
            if k == curses.KEY_RESIZE:
                world = None
                break
        if nxt < time.monotonic() - 1:
            nxt = time.monotonic()


def main():
    ap = argparse.ArgumentParser(description="Star Wars ASCII screensaver "
                                 "(q quit, r redraw, p pause, s superlaser, f Falcon, x torpedo run, c Razor Crest)")
    ap.add_argument("--fps", type=int, default=15, help="frames per second")
    args = ap.parse_args()
    try:
        curses.wrapper(run, max(1, args.fps))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()