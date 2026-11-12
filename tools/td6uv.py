"""Render a car's UV layout as a PNG guide (for painting skins).

Usage (run from the game folder):
  python tools/td6uv.py sky sky_uv.png             # texture with UV triangle edges on top
  python tools/td6uv.py sky sky_uv_plain.png --plain   # edges only, white on black

Output is 1024x1024 (the 256x256 texture scaled 4x). Reads cars/<id>.zip only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from td6car import encode_png, read_tga  # noqa: E402
from td6model import load  # noqa: E402

SIZE = 256
SCALE = 4
OUT = SIZE * SCALE
EDGE = (0, 200, 255, 255)


def line(img, x0, y0, x1, y1, color):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if 0 <= x0 < OUT and 0 <= y0 < OUT:
            img[(y0 * OUT + x0) * 4:(y0 * OUT + x0) * 4 + 4] = bytes(color)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def main(argv):
    plain = "--plain" in argv
    args = [a for a in argv if a != "--plain"]
    if len(args) != 2:
        sys.exit(__doc__)
    car, out = args
    verts, idx = load(car)
    img = bytearray(OUT * OUT * 4)
    if plain:
        img[3::4] = b"\xff" * (OUT * OUT)
        color = (255, 255, 255, 255)
    else:
        _, px = read_tga(car)
        for y in range(OUT):
            for x in range(OUT):
                s = ((y // SCALE) * SIZE + x // SCALE) * 4
                o = (y * OUT + x) * 4
                img[o:o + 4] = bytes((px[s + 2], px[s + 1], px[s], 255))
        color = EDGE
    # u,v in the file are top-left origin, same as the TGA rows
    pts = [(int(v[6] * OUT), int(v[7] * OUT)) for v in verts]
    for i in range(0, len(idx), 3):
        a, b, c = (pts[j] for j in idx[i:i + 3])
        for p, q in ((a, b), (b, c), (c, a)):
            line(img, p[0], p[1], q[0], q[1], color)
    with open(out, "wb") as f:
        f.write(encode_png(OUT, OUT, bytes(img)))
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
