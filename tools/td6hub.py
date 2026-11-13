"""Rim (wheel face) textures: cars/hubs.zip holds one <code>.tga per car, 64x64 24-bit.

Usage (from the game folder):
  python tools/td6hub.py import mcc rims/rim_clk500_64.png   # PNG (64x64, or 128/256/512: box-shrunk)
  python tools/td6hub.py export mcc mcc_rim.png

The game draws one shared wheel model (static.zip wheelhi.prr / wheello.prr) for every car and
puts this picture on its side. Rows are stored bottom-up or top-down as the TGA header says.
"""
import os
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from td6addcar import zip_members, zip_put  # noqa: E402
from td6car import encode_png  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUBS = os.path.join(ROOT, "cars", "hubs.zip")
SIZE = 64


def read_png(path):
    """8-bit RGB/RGBA non-interlaced PNG -> (w, h, rows of (r, g, b), top row first)."""
    b = open(path, "rb").read()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"{path}: not a PNG")
    pos, idat = 8, b""
    while pos < len(b):
        n, t = struct.unpack(">I4s", b[pos:pos + 8])
        data = b[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", data)
            if depth != 8 or ctype not in (2, 6) or inter:
                sys.exit(f"{path}: need an 8-bit RGB/RGBA non-interlaced PNG")
        elif t == b"IDAT":
            idat += data
    bpp = 4 if ctype == 6 else 3
    raw, stride = zlib.decompress(idat), w * bpp
    prev, rows, i = bytearray(stride), [], 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            up = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + up) & 255
            elif f == 3:
                line[x] = (line[x] + (a + up) // 2) & 255
            elif f == 4:
                p = a + up - c
                pa, pb, pc = abs(p - a), abs(p - up), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else up if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = line
    return w, h, rows


def shrink(w, h, rows):
    if w != h or w % SIZE:
        sys.exit(f"rim must be square and a multiple of {SIZE} pixels, got {w}x{h}")
    k = w // SIZE
    return [[tuple(sum(rows[y * k + j][x * k + i][c] for j in range(k) for i in range(k)) // (k * k)
                   for c in range(3)) for x in range(SIZE)] for y in range(SIZE)]


def hub_header(car):
    members = zip_members(HUBS)
    data = members.get(f"{car}.tga", members.get("xkr.tga"))[1]
    return data[:18]


def cmd_import(car, png):
    rows = shrink(*read_png(png))
    header = bytearray(hub_header(car))
    struct.pack_into("<HHBB", header, 12, SIZE, SIZE, 24, header[17] & 0x20)
    header[0] = 0                                   # no image id
    order = rows if header[17] & 0x20 else rows[::-1]  # bit 0x20 = top row first
    pixels = b"".join(bytes((b, g, r)) for row in order for r, g, b in row)
    zip_put(HUBS, f"{car}.tga", bytes(header) + pixels, replace=f"{car}.tga" in zip_members(HUBS))


def cmd_export(car, out):
    data = zip_members(HUBS)[f"{car}.tga"][1]
    w, h, bpp, desc = struct.unpack_from("<HHBB", data, 12)
    o, step = 18 + data[0], bpp // 8
    rows = [data[o + y * w * step:o + (y + 1) * w * step] for y in range(h)]
    if not desc & 0x20:
        rows.reverse()
    rgba = b"".join(bytes((r[x * step + 2], r[x * step + 1], r[x * step], 255)) for r in rows for x in range(w))
    open(out, "wb").write(encode_png(w, h, rgba))
    print(f"wrote {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["import"] and len(a) == 3:
        cmd_import(a[1].lower(), a[2])
    elif a[:1] == ["export"] and len(a) == 3:
        cmd_export(a[1].lower(), a[2])
    else:
        sys.exit(__doc__)
