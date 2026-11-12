"""Export Test Drive 6 car models (himodel.dat) to Wavefront OBJ.

Usage (run from the game folder):
  python tools/td6model.py export sky sky.obj
  python tools/td6model.py import sky sky.obj    # OBJ -> himodel.dat in cars/sky.zip
  python tools/td6model.py import sky low.obj --env   # OBJ -> envmodel.dat (low detail)
  python tools/td6model.py check            # validate layout on every car

Import keeps the original header and only updates the counts, offsets and
bounding radius (0x0C, f32, farthest vertex from origin). OBJ faces may use
v/vt/vn; polygons are fan-triangulated; at most 65535 distinct vertices.
Wheels are not part of himodel.dat (see the "hubs" archive).

himodel.dat layout (little endian), as decoded from the retail files:
  0x04  u32  mesh count (always 1)
  0x08  u32  vertex count
  0x4C  u32  index count (triangle list, u16 indices)
  0x50  u32  vertex data offset
  0x54  u32  index data offset
  vertex data starts on a 32-byte boundary, so 0-31 padding bytes follow the indices
  vertex = 8 x f32: x y z, nx ny nz, u v   (32 bytes)
Units match param/*.scr (1 unit ~ 1 game unit; car is ~1430 long on Z).
"""
import math
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from td6car import write_zip_member  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(car):
    data = zipfile.ZipFile(os.path.join(ROOT, "cars", car + ".zip")).read("himodel.dat")
    meshes, nverts = struct.unpack_from("<II", data, 4)
    nidx, voff, ioff = struct.unpack_from("<III", data, 0x4C)
    if meshes != 1 or voff + nverts * 32 != len(data) or not 0 <= voff - (ioff + nidx * 2) < 32 or nidx % 3:
        raise ValueError(f"{car}: unexpected layout")
    verts = [struct.unpack_from("<8f", data, voff + 32 * i) for i in range(nverts)]
    idx = struct.unpack_from(f"<{nidx}H", data, ioff)
    if max(idx) >= nverts:
        raise ValueError(f"{car}: index out of range")
    return verts, idx


def cmd_export(car, out):
    verts, idx = load(car)
    lines = [f"# TD6 {car}: {len(verts)} vertices, {len(idx) // 3} triangles"]
    lines += [f"v {v[0]:.9g} {v[1]:.9g} {v[2]:.9g}" for v in verts]
    lines += [f"vn {v[3]:.9g} {v[4]:.9g} {v[5]:.9g}" for v in verts]
    lines += [f"vt {v[6]:.9g} {1 - v[7]!r}" for v in verts]
    for i in range(0, len(idx), 3):
        a, b, c = (j + 1 for j in idx[i:i + 3])
        lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}")


def parse_obj(path):
    pos, nor, uv, faces = [], [], [], []
    with open(path) as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "v":
                pos.append(tuple(map(float, t[1:4])))
            elif t[0] == "vn":
                nor.append(tuple(map(float, t[1:4])))
            elif t[0] == "vt":
                uv.append((float(t[1]), 1 - float(t[2])))
            elif t[0] == "f":
                corners = []
                for c in t[1:]:
                    p = (c.split("/") + ["", ""])[:3]
                    corners.append(tuple(int(x) - 1 if x else -1 for x in p))
                for k in range(1, len(corners) - 1):
                    faces.append((corners[0], corners[k], corners[k + 1]))
    return pos, nor, uv, faces


def cmd_import(car, src, member="himodel.dat"):
    pos, nor, uv, faces = parse_obj(src)
    keys = sorted({c for tri in faces for c in tri})
    if len(keys) > 65535:
        sys.exit(f"too many vertices: {len(keys)} (max 65535)")
    slot = {k: i for i, k in enumerate(keys)}
    verts = []
    for p, t, n in keys:
        verts.append(pos[p] + (nor[n] if n >= 0 else (0.0, 1.0, 0.0)) + (uv[t] if t >= 0 else (0.0, 0.0)))
    idx = [slot[c] for tri in faces for c in tri]
    path = os.path.join(ROOT, "cars", car + ".zip")
    old = zipfile.ZipFile(path).read(member)
    ioff = struct.unpack_from("<I", old, 0x54)[0]
    voff = -(-(ioff + len(idx) * 2) // 32) * 32
    head = bytearray(old[:ioff])
    radius = max(math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in verts)
    struct.pack_into("<I", head, 0x08, len(verts))
    struct.pack_into("<f", head, 0x0C, radius)
    struct.pack_into("<I", head, 0x30, voff)
    struct.pack_into("<III", head, 0x48, len(verts), len(idx), voff)
    out = bytes(head) + struct.pack(f"<{len(idx)}H", *idx)
    out += bytes(voff - len(out)) + b"".join(struct.pack("<8f", *v) for v in verts)
    write_zip_member(car, member, out)
    print(f"updated {member} in cars/{car}.zip: {len(verts)} verts, {len(idx) // 3} tris")


def cmd_check():
    cars = sorted(f[:-4] for f in os.listdir(os.path.join(ROOT, "cars")) if f.endswith(".zip"))
    ok = bad = 0
    for car in cars:
        try:
            verts, idx = load(car)
            ok += 1
            print(f"{car}: {len(verts)} verts, {len(idx) // 3} tris")
        except (KeyError, ValueError, zipfile.BadZipFile) as e:
            bad += 1
            print(f"{car}: skipped ({e})")
    print(f"ok={ok} skipped={bad}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["export"] and len(a) == 3:
        cmd_export(a[1], a[2])
    elif a[:1] == ["import"] and len(a) == 3:
        cmd_import(a[1], a[2])
    elif a[:1] == ["import"] and len(a) == 4 and a[3] == "--env":
        cmd_import(a[1], a[2], "envmodel.dat")
    elif a == ["check"]:
        cmd_check()
    else:
        print(__doc__)
        sys.exit(1)
