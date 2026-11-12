"""Edit Test Drive 6 cars: export/import body texture, set handling values.

Usage (run from the game folder):
  python tools/td6car.py list
  python tools/td6car.py export sky sky.png      # carbody.tga -> PNG
  python tools/td6car.py import sky sky.png      # PNG -> carbody.tga in cars/sky.zip
  python tools/td6car.py set sky MAX_SPEED=900 PEAK_TORQUE=120
  python tools/td6car.py clone aud lit att       # put aud's model+texture into slot lit, use att's handling

The game only loads the 45 cars in its built-in table, so a new car has to
overwrite an existing slot. envmodel.dat falls back to himodel.dat if the
source car has none.

Textures are 256x256 32-bit TGA (BGRA, top-left origin). PNG must be 8-bit
RGB or RGBA, non-interlaced, 256x256. The game tints the body, so the
original texture is a yellow mask rather than the in-game colour.
"""
import os
import re
import shutil
import struct
import sys
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = "carbody.tga"


def zip_path(car):
    return os.path.join(ROOT, "cars", car + ".zip")


def read_tga(car):
    data = zipfile.ZipFile(zip_path(car)).read(TEX)
    w, h, bpp = struct.unpack("<HHB", data[12:17])
    if (data[2], w, h, bpp) != (2, 256, 256, 32):
        sys.exit(f"unexpected TGA format in {car}: type={data[2]} {w}x{h}x{bpp}")
    return data[:18], data[18:18 + w * h * 4]


def write_zip_member(car, name, payload):
    path = zip_path(car)
    tmp = path + ".new"
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zi.infolist():
            zo.writestr(info, payload if info.filename == name else zi.read(info.filename))
    os.replace(tmp, path)


def chunk(tag, body):
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))


def encode_png(w, h, rgba):
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def decode_png(blob):
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit("not a PNG file")
    pos, idat, ihdr = 8, b"", None
    while pos < len(blob):
        n, tag = struct.unpack(">I4s", blob[pos:pos + 8])
        body = blob[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype, _, _, interlace = ihdr
    if (w, h, depth, interlace) != (256, 256, 8, 0) or ctype not in (2, 6):
        sys.exit("PNG must be 256x256, 8-bit RGB or RGBA, non-interlaced")
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride, out, prev = w * bpp, bytearray(), bytearray(w * bpp)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out += line
        prev = line
    if bpp == 3:
        rgba = bytearray()
        for i in range(0, len(out), 3):
            rgba += out[i:i + 3] + b"\xff"
        return bytes(rgba)
    return bytes(out)


def cmd_list():
    names = sorted(f[:-4] for f in os.listdir(os.path.join(ROOT, "cars")) if f.endswith(".zip"))
    print(" ".join(names))


def cmd_export(car, out):
    _, px = read_tga(car)
    rgba = bytearray(len(px))
    for i in range(0, len(px), 4):
        rgba[i:i + 4] = bytes((px[i + 2], px[i + 1], px[i], px[i + 3]))
    with open(out, "wb") as f:
        f.write(encode_png(256, 256, bytes(rgba)))
    print(f"wrote {out}")


def cmd_import(car, src):
    header, _ = read_tga(car)
    with open(src, "rb") as f:
        rgba = decode_png(f.read())
    bgra = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        bgra[i:i + 4] = bytes((rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3]))
    write_zip_member(car, TEX, header + bytes(bgra))
    print(f"updated {TEX} in cars/{car}.zip")


def cmd_set(car, pairs):
    path = os.path.join(ROOT, "param", car + "param.scr")
    with open(path, "rb") as f:
        text = f.read().decode("ascii")
    for pair in pairs:
        key, _, value = pair.partition("=")
        text, n = re.subn(rf"(?m)^:{re.escape(key)}:[^\r\n]*", f":{key}:{value}", text)
        if n != 1:
            sys.exit(f"key not found: {key}")
        print(f"{key} = {value}")
    with open(path, "wb") as f:
        f.write(text.encode("ascii"))


def cmd_clone(src, dst, params):
    zs = zipfile.ZipFile(zip_path(src))
    for name in ("himodel.dat", TEX):
        write_zip_member(dst, name, zs.read(name))
    env = zs.read("envmodel.dat") if "envmodel.dat" in zs.namelist() else zs.read("himodel.dat")
    write_zip_member(dst, "envmodel.dat", env)
    shutil.copyfile(os.path.join(ROOT, "param", params + "param.scr"),
                    os.path.join(ROOT, "param", dst + "param.scr"))
    print(f"cars/{dst}.zip <- {src} model/texture; param/{dst}param.scr <- {params}")


def main(argv):
    cmds = {"list": (cmd_list, 0), "export": (cmd_export, 2), "import": (cmd_import, 2)}
    if argv and argv[0] == "set" and len(argv) >= 3:
        return cmd_set(argv[1], argv[2:])
    if argv and argv[0] == "clone" and len(argv) == 4:
        return cmd_clone(*argv[1:])
    if argv and argv[0] in cmds and len(argv) - 1 == cmds[argv[0]][1]:
        return cmds[argv[0]][0](*argv[1:])
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
