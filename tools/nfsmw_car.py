"""Convert an NFS Most Wanted (2005) car GEOMETRY.BIN into Test Drive 6 ready files.

Usage (from the game folder):
  python tools/nfsmw_car.py GEOMETRY.BIN OUTDIR [--car CLK500] [--kit KIT00] [--scale 320]
  python tools/nfsmw_car.py GEOMETRY.BIN --list          # object names

Writes to OUTDIR: hi.obj (detail level A), env.obj (level B), texture.png (256x256, one flat
colour square per material kind, body = the game's yellow paint mask), info.txt (wheel
centres and size in game units). Then import with td6model.py / td6car.py as usual.

GEOMETRY.BIN layout (chunk = u32 id, u32 size; ids with bit 31 hold chunks), as read here:
  0x80134000 solid list > 0x80134010 object >
    0x134011 header: bbox at +0x20/+0x30, 4x4 matrix at +0x40, name at +0xa0
    0x80134100 mesh > 0x134b02 materials (0x68 bytes each, after 0x11 padding: +0x3c vertex
      count, +0x40 triangle count, +0x44 first index), 0x134b01 vertices (36 bytes: position,
      normal, shade, uv), 0x134b03 u16 indices (absolute in the object), 0x134c02 one
      material name per material, in order
  Car space: +X forward, +Y left, +Z up, metres. Wheels are not placed in the geometry
  (the game's car database does that), so wheel centres are taken from the wheel arches.
"""
import os
import struct
import sys

PAINT_MASK = (217, 184, 0)
# body panels that take the paint colour
PAINT = {"BODY", "BODY_LEFT", "BODY_RIGHT", "BODY_REAR", "BODY_FRONT", "BODY_TOP", "BODY_HOOD",
         "BODY_PLAINNOTHING"}
# first matching keyword wins; colours keep R and B >= 1 so the game never paints them
COLOURS = [
    ("BRAKELIGHT", (170, 20, 24)), ("TAILLIGHT", (170, 20, 24)), ("REVERSE", (225, 225, 220)),
    ("BULB", (230, 230, 220)), ("MASK", (20, 20, 22)), ("WINDOW", (30, 38, 48)),
    ("_GLASS", (200, 205, 210)), ("CLEAR_PLASTIC", (190, 195, 200)),
    ("LICENSE_PLATE", (225, 225, 220)), ("CHROME", (205, 208, 212)), ("BADGING", (200, 200, 205)),
    ("ALUMINUM", (175, 178, 182)), ("DOORLINE", (20, 20, 22)), ("GRILL", (30, 30, 32)),
    ("DULL_PLASTIC", (38, 38, 40)), ("MOLDING", (38, 38, 40)), ("BOTTOM", (25, 25, 27)),
    ("MISC", (60, 60, 62)), ("BLACK", (20, 20, 22)),
]
DEFAULT = (120, 120, 122)
# stock parts of a car (per kit); damage, decals, driver, interior, brakes and tyres are left out
PARTS = ["BASE", "{kit}_BODY", "{kit}_HOOD", "{kit}_SPOILER", "{kit}_FRONT_WINDOW", "{kit}_REAR_WINDOW",
         "{kit}_FRONT_LEFT_WINDOW", "{kit}_FRONT_RIGHT_WINDOW", "{kit}_REAR_LEFT_WINDOW",
         "{kit}_REAR_RIGHT_WINDOW", "{kit}_LEFT_HEADLIGHT", "{kit}_RIGHT_HEADLIGHT",
         "{kit}_LEFT_HEADLIGHT_GLASS", "{kit}_RIGHT_HEADLIGHT_GLASS", "{kit}_LEFT_BRAKELIGHT",
         "{kit}_RIGHT_BRAKELIGHT", "{kit}_LEFT_SIDE_MIRROR", "{kit}_RIGHT_SIDE_MIRROR"]


def chunks(d, off, end):
    while off + 8 <= end:
        cid, size = struct.unpack_from("<II", d, off)
        yield cid, off + 8, size
        off += 8 + size


def skip_pad(d, off):
    while d[off:off + 4] == b"\x11\x11\x11\x11":
        off += 4
    return off


def read_objects(path):
    d = open(path, "rb").read()
    objs = {}
    for cid, off, size in chunks(d, 0, len(d)):
        if cid != 0x80134000:
            continue
        for oid, ooff, osize in chunks(d, off, off + size):
            if oid != 0x80134010:
                continue
            sub = list(chunks(d, ooff, ooff + osize))
            hdr = next(c for c in sub if c[0] == 0x134011)
            name = d[hdr[1] + 0xA0:hdr[1] + hdr[2]].split(b"\0")[0].decode("latin1")
            mesh = next((c for c in sub if c[0] == 0x80134100), None)
            if not mesh:
                continue
            mc = list(chunks(d, mesh[1], mesh[1] + mesh[2]))
            mo, ms = next((o, s) for c, o, s in mc if c == 0x134B02)
            vo, vs = next((o, s) for c, o, s in mc if c == 0x134B01)
            io, isz = next((o, s) for c, o, s in mc if c == 0x134B03)
            names = [d[o:o + s].split(b"\0")[0].decode("latin1") for c, o, s in mc if c == 0x134C02]
            mo2, vo2, io2 = skip_pad(d, mo), skip_pad(d, vo), skip_pad(d, io)
            mats = []
            for k in range((ms - (mo2 - mo)) // 0x68):
                nv, nt, first = struct.unpack_from("<III", d, mo2 + 0x68 * k + 0x3C)
                mats.append((names[k] if k < len(names) else "?", nt, first))
            nverts = (vs - (vo2 - vo)) // 36
            verts = [struct.unpack_from("<6f", d, vo2 + 36 * i) for i in range(nverts)]
            idx = struct.unpack_from(f"<{(isz - (io2 - io)) // 2}H", d, io2)
            objs[name] = (verts, idx, mats)
    return objs


def colour_of(mat):
    base = mat.upper()
    if base in PAINT or any(base.endswith("_" + p) for p in ("BODY_LEFT", "BODY_RIGHT", "BODY_TOP")):
        return PAINT_MASK
    return next((rgb for key, rgb in COLOURS if key in base), DEFAULT)


def collect(objs, car, kit, lod):
    tris = []   # (3 positions, 3 normals, colour)
    used = []
    for part in PARTS:
        name = f"{car}_{part.format(kit=kit)}_{lod}"
        if name not in objs:
            continue
        used.append(name)
        verts, idx, mats = objs[name]
        for mat, nt, first in mats:
            rgb = colour_of(mat)
            for t in range(nt):
                a, b, c = idx[first + 3 * t:first + 3 * t + 3]
                tris.append(([verts[i][:3] for i in (a, b, c)], [verts[i][3:6] for i in (a, b, c)], rgb))
    return tris, used


def wheel_arches(tris):
    """Arch centres along X from the side profile of the painted body: its lowest point per
    X slice stays high over the wheel openings. Returns the two longest high runs."""
    pts = [p for ps, _, rgb in tris for p in ps if rgb == PAINT_MASK]
    xmin, xmax = min(p[0] for p in pts), max(p[0] for p in pts)
    ymax = max(abs(p[1]) for p in pts)
    bins = 48                     # about 10 cm slices; finer slices leave too many empty ones
    low = [None] * bins
    for x, y, z in pts:
        if abs(y) > ymax * 0.85:
            k = min(bins - 1, int((x - xmin) / (xmax - xmin) * bins))
            low[k] = z if low[k] is None else min(low[k], z)
    ground = min(v for v in low if v is not None)
    runs, cur = [], []
    for i, v in enumerate(low):
        if v is not None and v > ground + 0.3:
            cur.append(i)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    runs = sorted(runs, key=len, reverse=True)[:2]
    centres = sorted(xmin + (r[0] + r[-1] + 1) / 2 / bins * (xmax - xmin) for r in runs)
    arch_top = min(max(low[i] for i in r) for r in runs)    # lower of the two arch peaks
    return centres, ground, arch_top, ymax


def tyre_size(objs, car, kit):
    """Tyre radius and width from the front tyre object (modelled at the origin)."""
    name = f"{car}_{kit}_FRONT_TIRE_A"
    if name not in objs:
        return 0.33, 0.22
    vs = objs[name][0]
    radius = (max(v[2] for v in vs) - min(v[2] for v in vs)) / 2
    width = max(v[1] for v in vs) - min(v[1] for v in vs)
    return radius, width


def write_obj(path, tris, swatch, centre, scale):
    # game: +X right = -Y, +Y up = Z, +Z front = X (a mirror, det -1)
    def g(p):
        return ((-(p[1] - centre[1])) * scale, (p[2] - centre[2]) * scale, (p[0] - centre[0]) * scale)

    def gn(n):
        return (-n[1], n[2], n[0])

    # retail winding: cross(b-a, c-a) opposite the outward (vertex) normal
    agree = 0
    for ps, ns, _ in tris:
        a, b, c = map(g, ps)
        u = [b[k] - a[k] for k in range(3)]
        w = [c[k] - a[k] for k in range(3)]
        cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        n = [sum(gn(x)[k] for x in ns) for k in range(3)]
        agree += sum(cr[k] * n[k] for k in range(3)) > 0
    flip = agree > len(tris) / 2
    with open(path, "w") as f:
        f.write(f"# {len(tris)} triangles\n")
        for ps, ns, rgb in tris:
            order = (0, 2, 1) if flip else (0, 1, 2)
            u, v = swatch[rgb]
            for k in order:
                f.write("v %.4f %.4f %.4f\n" % g(ps[k]))
                f.write("vn %.5f %.5f %.5f\n" % gn(ns[k]))
                f.write(f"vt {u:.6f} {v:.6f}\n")
        for t in range(len(tris)):
            a = 3 * t + 1
            f.write(f"f {a}/{a}/{a} {a + 1}/{a + 1}/{a + 1} {a + 2}/{a + 2}/{a + 2}\n")
    return flip


def write_texture(path, colours):
    """Flat colour squares, 16 per row from the bottom-left (Blender/OBJ v up), and the
    matching OBJ uv for each colour."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from td6car import encode_png
    cell, swatch = 16, {}
    img = [[(0, 0, 0)] * 256 for _ in range(256)]            # rows top first
    for k, rgb in enumerate(colours):
        cx, cy = k % 16, k // 16
        for y in range(cell):
            for x in range(cell):
                img[255 - (cy * cell + y)][cx * cell + x] = rgb
        swatch[rgb] = ((cx + 0.5) / 16, (cy + 0.5) / 16)
    # everything but the paint square keeps R and B >= 1 so the game never paints it
    rgba = b"".join(bytes((r, g, b, 255)) if (r, g, b) == PAINT_MASK else bytes((max(r, 1), g, max(b, 1), 255))
                    for row in img for r, g, b in row)
    open(path, "wb").write(encode_png(256, 256, rgba))
    return swatch


def main():
    a = sys.argv[1:]
    opt = {"--car": None, "--kit": "KIT00", "--scale": "320"}
    pos, i = [], 0
    while i < len(a):
        if a[i] in opt:
            opt[a[i]] = a[i + 1]
            i += 2
        else:
            pos.append(a[i])
            i += 1
    objs = read_objects(pos[0])
    if "--list" in pos:
        print("\n".join(sorted(objs)))
        return
    out, scale = pos[1], float(opt["--scale"])
    car = opt["--car"] or next(n.split("_")[0] for n in objs if n.endswith("_BASE_A"))
    os.makedirs(out, exist_ok=True)
    hi, used = collect(objs, car, opt["--kit"], "A")
    env, _ = collect(objs, car, opt["--kit"], "B")
    if not env:
        env = hi
    colours = sorted({rgb for _, _, rgb in hi + env}, key=lambda c: c != PAINT_MASK)
    swatch = write_texture(os.path.join(out, "texture.png"), colours)
    pts = [p for ps, _, _ in hi for p in ps]
    lo = [min(p[k] for p in pts) for k in range(3)]
    up = [max(p[k] for p in pts) for k in range(3)]
    centre = [(lo[k] + up[k]) / 2 for k in range(3)]
    flip = write_obj(os.path.join(out, "hi.obj"), hi, swatch, centre, scale)
    write_obj(os.path.join(out, "env.obj"), env, swatch, centre, scale)
    arches, ground, arch_top, body_half = wheel_arches(hi)
    radius, width = tyre_size(objs, car, opt["--kit"])
    # sideways from the painted body (mirrors excluded): tyre face just inside the body side
    half_track = body_half - width / 2 - 0.03
    # height from the arch: the body reaches below z = 0, so z = 0 is not the ground (CLK test:
    # wheels 50 units too high poked through the fenders); tyre top just under the arch
    wz = arch_top - radius - 0.01
    with open(os.path.join(out, "info.txt"), "w") as f:
        f.write(f"car {car}, parts: {', '.join(used)}\n")
        f.write(f"hi triangles: {len(hi)}\nenv triangles: {len(env)}\nwinding flipped: {flip}\n")
        f.write("size (game units) x %.0f y %.0f z %.0f\n" % ((up[1] - lo[1]) * scale, (up[2] - lo[2]) * scale,
                                                              (up[0] - lo[0]) * scale))
        f.write("materials: " + ", ".join(sorted({m for n in used for m, _, _ in objs[n][2]})) + "\n")
        f.write("arch centres (game z): " + ", ".join("%.0f" % ((x - centre[0]) * scale) for x in arches) + "\n")
        f.write("ground (game y): %.0f\n" % ((ground - centre[2]) * scale))
        f.write("tyre radius %.3f m, width %.3f m\n" % (radius, width))
        # the game draws its tyre at about 0.6 x WHEEL_RADIUS (190E and remaster cars)
        f.write("WHEEL_RADIUS:%.0f\n" % (radius * scale / 0.6))
        # retail order: front left, front right, rear left, rear right
        for k, x in enumerate(sorted(arches, reverse=True) * 1):
            for side in (-1, 1):
                f.write("WHEEL_CENTRES%d:{%.0f,%.0f,%.0f}\n" % (2 * k + (side > 0), side * half_track * scale,
                                                                (wz - centre[2]) * scale, (x - centre[0]) * scale))
    print(open(os.path.join(out, "info.txt")).read())


if __name__ == "__main__":
    main()
