"""Add new cars to Test Drive 6 (writes a COPY of an exe plus new asset files).

Usage (run from the game folder):
  python tools/td6addcar.py tools/newcars.json --base TD6_remaster.exe --out TD6_mod.exe

The car list (JSON, see tools/newcars.json) names each new car's code, the exe record it is
copied from ("from": "<exe>:<code>", exe = base or a key of "exes"), the files it is copied
from ("files": "<root>:<code>"), the single-race list position ("after": code) and optional
overrides: name, full, class (1-4), price, logo (logo name), text (the 12 info screen lines,
first char = colour, y yellow / w white). Cars get ids 45, 46, ... in list
order, so entries must only ever be appended (saves store car ids).
Also: "logos" appends logo slots (name, file in frontend.zip, image source), "frontend_restore"
replaces frontend.zip members, "logo_fixes" sets the logo of existing cars.

What the exe copy gets (see tools/FINDINGS.md, "Adding a 46th car" and later sections):
  - a new section .td6mod holding the car table, paint table, car info text table, single-race
    car list 1 (new cars appended), the single-race display order list, the single-race list
    buffer, the logo name table and logo sprite handles, and all new strings
  - every code reference to those tables repointed, the car count 45 and logo count 19 raised,
    and the two single-race list builders' stack buffers grown from 45 to 61 entries
Base and TD6.exe are never modified. Existing asset files are only extended (zip members added,
or frontend.zip members replaced as listed).
"""
import argparse
import json
import os
import shutil
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.path.join(ROOT, "TD6.exe")
B = 0x400000
TEXT_LO, TEXT_HI = 0x401000, 0x46D000   # .text, for reference scans

CARS, REC = 45, 24
CAR_TABLE, PAINT, PAINT_ROW = 0x481078, 0x4814B0, 12
LIST1, LIST1_BOUND = 0x480E0C, 0x480E68
GROUPS = [0x480E0C, 0x480E2C, 0x480E3C, 0x480E40, 0x480E4C, 0x480E50, 0x480E5C, 0x480E60, 0x480E6C]

CAR_REFS = [int(x, 16) for x in """
414b08 4153bc 415b2a 415ddd 4163aa 416499 41655b 4165a9 416811 4168ae 4176cf 4178bd 417933
419d04 41a7cb 41a87f 41d304 41d4c5 41d4de 41e0e5 41e17c 41e3d6 41e43a 41f183 420b65 421443
421c4b 42363e 4236f7 4244ec 42457a 424708 424785 42619c 42a3d4 43618a 459efe 459f5f 45b914
45b973 45ba2e 45ba9b""".split()]
PAINT_REFS = [int(x, 16) for x in """
41633f 41a955 41a985 41d69b 41da4a 41dae3 41db80 41dc19 41dca9 41dd6c 41de61 41df22 41e1b0
""".split()]
CAR_END_REF = 0x41A813            # cmp edx, 0x4814c0 (price field end pointer)
TEXT, TEXT_LINES = 0x4724D8, 12   # car info screen: 12 string pointers per car
TEXT_REF = 0x4183C4               # mov esi, [eax*4 + 0x4724d8]
LIST_REFS = [0x41400D, 0x414BC3]  # mov eax, 0x480e0c
BOUND_REFS = [0x414032, 0x414BE8]  # cmp eax, 0x480e68
# (address, original bytes, patched bytes with {n} = new car count as hex byte)
COUNT_PATCHES = [
    (0x41D320, "663d2d00", "663d{n}00"),   # cmp ax, imm16
    (0x41D4FA, "663d2d00", "663d{n}00"),
    (0x41D500, "6a2d", "6a{n}"),           # push imm8 (signed: max 127)
    (0x41E111, "6683f92d", "6683f9{n}"),   # cmp cx, imm8 (signed: max 127)
    (0x41E1C9, "6683fb2d", "6683fb{n}"),
]

# single-race car list: built by 0x414000 and 0x414b30 into a count word + ids buffer, then
# sorted through the display order list into a 0x5c-byte stack buffer and copied back
RACE_BUF, RACE_BUF_END = 0x65DB4E, 0x65DBAC       # count word, ids from +2; next var at end
RACE_REF_COUNTS = {0x65DB4E: 40, 0x65DB50: 4}
ORDER, ORDER_END = 0x472020, 0x47207A               # u16 ids, 0xff end, 45 max
ORDER_REF_COUNTS = {0x472020: 2, 0x47207A: 2}
RACE_MAX = 61                                        # (0x7c - 2) / 2
STACK_PATCHES = [
    (0x414000, "83ec5c", "83ec7c"), (0x4141DF, "83c45c", "83c47c"), (0x4141CC, "b917000000", "b91f000000"),
    (0x414B35, "83ec5c", "83ec7c"), (0x414B52, "83c45c", "83c47c"), (0x414DAC, "83c45c", "83c47c"),
    (0x414D89, "b917000000", "b91f000000"),
]

# logos: 19 x (name ptr, 0) at 0x481f50, loaded as <name>.tga from frontend.zip into u16
# sprite handles at 0x65b440 (0x65b468 is another variable, so the handles move too)
LOGOS, LOGO_COUNT = 0x481F50, 19
LOGO_NAME_REF_COUNTS = {0x481F50: 1}
LOGO_BOUND_AT = 0x42360A          # cmp esi, 0x481fe8 (other 0x481fe8 hits are another table)
LOGO_HANDLES = 0x65B440
LOGO_HANDLE_REF_COUNTS = {0x65B440: 5}
LOGO_COUNT_PATCH = (0x42364B, "ba13000000", "ba{n}000000")   # mov edx, 0x13

# layout of the new section. The game reads per-car tables with unchecked byte ids, including
# 0xff for empty dealer slots (0x41633f), so each per-car table has room for all 256 ids.
SEC_SIZE = 0x10000
OFF_CARS, OFF_PAINT, OFF_LIST, OFF_ORDER = 0x0000, 0x1800, 0x2400, 0x2480
OFF_RACE, OFF_LOGOS, OFF_HANDLES, OFF_TEXT, OFF_STR = 0x2500, 0x2600, 0x2700, 0x3000, 0x6000
assert OFF_CARS + 256 * REC <= OFF_PAINT and OFF_PAINT + 256 * PAINT_ROW <= OFF_LIST
assert OFF_TEXT + 256 * TEXT_LINES * 4 <= OFF_STR


def rd(d, va, n=4):
    return bytes(d[va - B:va - B + n])


def u32(d, va):
    return struct.unpack_from("<I", d, va - B)[0]


def cstr(d, va):
    o = va - B
    return bytes(d[o:d.index(b"\0", o)]).decode("latin1")


def car_codes(d):
    return [cstr(d, u32(d, CAR_TABLE + i * REC + 8)).lower() for i in range(CARS)]


def u16_list(d, va):
    ids = []
    while (v := struct.unpack_from("<H", d, va - B + 2 * len(ids))[0]) != 0xFF:
        ids.append(v)
    return ids


def repoint(d, ins, lo, hi, new_of):
    """Replace the one imm32/disp32 in [lo, hi) inside the instruction at ins."""
    window = rd(d, ins, 12)
    hits = [i for i in range(9) if lo <= struct.unpack_from("<I", window, i)[0] < hi]
    if len(hits) != 1:
        sys.exit(f"unexpected bytes at 0x{ins:x}: {window.hex()}")
    old = struct.unpack_from("<I", window, hits[0])[0]
    struct.pack_into("<I", d, ins - B + hits[0], new_of(old))


def move_refs(d, counts, delta):
    """Add delta to every dword in .text equal to a key of counts; check the hit counts."""
    for value, want in counts.items():
        pat, at, hits = struct.pack("<I", value), TEXT_LO - B, []
        while (at := d.find(pat, at, TEXT_HI - B)) != -1:
            hits.append(at)
            at += 1
        if len(hits) != want:
            sys.exit(f"0x{value:x}: {len(hits)} references, expected {want}")
        for at in hits:
            struct.pack_into("<I", d, at, value + delta)


def patch(d, va, old, new):
    if rd(d, va, len(old) // 2).hex() != old:
        sys.exit(f"unexpected bytes at 0x{va:x}")
    d[va - B:va - B + len(new) // 2] = bytes.fromhex(new)


def add_section(d, name, size):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = pe + 24
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    hdr = opt + struct.unpack_from("<H", d, pe + 20)[0] + nsec * 40
    # the slot must lie in the header padding before the first section's data; the remaster
    # exe has a stray tool tag ("SUN/CLS") there, which the loader ignores
    first_raw = min(struct.unpack_from("<I", d, hdr - 40 * (i + 1) + 20)[0] for i in range(nsec))
    if hdr + 40 > first_raw:
        sys.exit("no room for a new section header")
    va = struct.unpack_from("<I", d, opt + 56)[0]      # SizeOfImage, already page aligned
    raw = len(d)
    struct.pack_into("<8sIIIIIIHHI", d, hdr, name, size, va, size, raw, 0, 0, 0, 0, 0xC0000040)
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    struct.pack_into("<I", d, opt + 56, va + size)
    d.extend(bytes(size))
    return B + va, raw


# rd/u32/cstr/repoint use file offset == VA - base, true for the original sections only


def build_exe(spec, base_path, out):
    d = bytearray(open(base_path, "rb").read())
    exes = {"base": bytes(d)}
    for key, path in spec.get("exes", {}).items():
        exes[key] = open(os.path.join(ROOT, path), "rb").read()
    codes = car_codes(d)
    logo_names = [cstr(d, u32(d, LOGOS + 8 * i)) for i in range(LOGO_COUNT)]
    logo_names += [lg["name"] for lg in spec.get("logos", [])]
    cars = spec["cars"]
    n = CARS + len(cars)
    if n > 127 or len(logo_names) > 32:
        sys.exit("too many cars or logos")

    base, sec = add_section(d, b".td6mod", SEC_SIZE)  # VA for pointers, file offset for writes
    va = {k: base + o for k, o in (("cars", OFF_CARS), ("paint", OFF_PAINT), ("list", OFF_LIST),
                                   ("order", OFF_ORDER), ("race", OFF_RACE), ("logos", OFF_LOGOS),
                                   ("handles", OFF_HANDLES), ("text", OFF_TEXT))}
    pool = bytearray()

    def string(s):
        ptr = base + OFF_STR + len(pool)
        pool.extend(s.encode("latin1") + b"\0")
        return ptr

    def put(off, data):
        d[sec + off:sec + off + len(data)] = data

    # existing tables, copied as they are
    put(OFF_CARS, rd(d, CAR_TABLE, CARS * REC))
    put(OFF_PAINT, rd(d, PAINT, CARS * PAINT_ROW))
    put(OFF_TEXT, rd(d, TEXT, CARS * TEXT_LINES * 4))
    for i in range(LOGO_COUNT):
        put(OFF_LOGOS + 8 * i, rd(d, LOGOS + 8 * i, 8))
    for k, lg in enumerate(spec.get("logos", [])):
        put(OFF_LOGOS + 8 * (LOGO_COUNT + k), struct.pack("<II", string(lg["name"]), 0))

    def logo_index(name):
        if name not in logo_names:
            sys.exit(f"unknown logo {name}; known: {logo_names}")
        return logo_names.index(name)

    for code, logo in spec.get("logo_fixes", {}).items():
        sec_rec = sec + OFF_CARS + codes.index(code) * REC
        d[sec_rec + 20] = logo_index(logo)

    # new cars
    all_codes = list(codes)
    for k, car in enumerate(cars):
        cid = CARS + k
        code = car["code"].lower()
        if len(code) != 3 or not code.isalnum() or code in all_codes:
            sys.exit(f"bad or duplicate code {code}")
        src_exe, src_code = car["from"].split(":")
        sd = exes[src_exe]
        sid = car_codes(sd).index(src_code)
        rec = bytearray(sd[CAR_TABLE - B + sid * REC:CAR_TABLE - B + (sid + 1) * REC])
        full = car.get("full", cstr(sd, struct.unpack_from("<I", rec, 0)[0]))
        name = car.get("name", cstr(sd, struct.unpack_from("<I", rec, 4)[0]))
        cls, price = struct.unpack_from("<II", rec, 12)
        cls = car["class"] - 1 if "class" in car else cls
        price = car.get("price", price)
        struct.pack_into("<IIIII", rec, 0, string(full), string(name), string(code.upper()), cls, price)
        if "logo" in car:
            rec[20] = logo_index(car["logo"])
        put(OFF_CARS + cid * REC, rec)
        put(OFF_PAINT + cid * PAINT_ROW, sd[PAINT - B + sid * PAINT_ROW:PAINT - B + (sid + 1) * PAINT_ROW])
        lines = [cstr(sd, u32(sd, TEXT + (sid * TEXT_LINES + j) * 4)) for j in range(TEXT_LINES)]
        if "full" in car:
            lines[0] = "y" + full
        if "text" in car:
            if len(car["text"]) != TEXT_LINES:
                sys.exit(f"{code}: text needs {TEXT_LINES} lines")
            lines = car["text"]
        put(OFF_TEXT + cid * TEXT_LINES * 4, struct.pack(f"<{TEXT_LINES}I", *map(string, lines)))
        all_codes.append(code)
        print(f"car {cid} {code}: {name} | {full}, class {cls + 1}, price {price}, from {car['from']}")

    # per-class limits: dealer and garage lists have 20 slots, opponent picker buffer 48
    classes = [d[sec + OFF_CARS + i * REC + 12] for i in range(n)]
    for c in range(4):
        if classes.count(c) > 20:
            sys.exit(f"class {c + 1} has {classes.count(c)} cars, max 20")
    print("cars per class:", [classes.count(c) for c in range(4)])

    # single-race lists: group 1 gets the new cars; display order gets each after its "after"
    group1 = u16_list(d, LIST1) + list(range(CARS, n))
    total = sum(len(u16_list(d, g)) for g in GROUPS) + len(cars)
    order = u16_list(d, ORDER)
    for k, car in enumerate(cars):
        order.insert(order.index(all_codes.index(car["after"])) + 1, CARS + k)
    if len(group1) > (LIST1_BOUND - LIST1) // 2 or total > RACE_MAX or len(order) > RACE_MAX:
        sys.exit(f"single-race lists too long: group 1 {len(group1)}, all {total}, order {len(order)}")
    put(OFF_LIST, struct.pack(f"<{len(group1) + 1}H", *group1, 0xFF))
    put(OFF_ORDER, struct.pack(f"<{len(order) + 1}H", *order, 0xFF))
    print(f"single race: group 1 {len(group1)} ids, all groups {total}, order list {len(order)}")

    if OFF_STR + len(pool) > SEC_SIZE:
        sys.exit("string pool full")
    put(OFF_STR, pool)

    # code references
    if len(CAR_REFS) != 42 or len(PAINT_REFS) != 13:
        sys.exit("reference lists damaged")
    car_end = CAR_TABLE + CARS * REC
    for ins in CAR_REFS:
        repoint(d, ins, CAR_TABLE, car_end, lambda old: va["cars"] + old - CAR_TABLE)
    for ins in PAINT_REFS:
        repoint(d, ins, PAINT, PAINT + CARS * PAINT_ROW, lambda old: va["paint"] + old - PAINT)
    repoint(d, CAR_END_REF, car_end + 16, car_end + 17, lambda old: va["cars"] + n * REC + 16)
    repoint(d, TEXT_REF, TEXT, TEXT + CARS * TEXT_LINES * 4, lambda old: va["text"] + old - TEXT)
    for ref in LIST_REFS:
        repoint(d, ref - 1, LIST1, LIST1 + 1, lambda old: va["list"])
    for ref in BOUND_REFS:
        repoint(d, ref - 1, LIST1_BOUND, LIST1_BOUND + 1, lambda old: va["list"] + LIST1_BOUND - LIST1)
    move_refs(d, RACE_REF_COUNTS, va["race"] - RACE_BUF)
    move_refs(d, ORDER_REF_COUNTS, va["order"] - ORDER)
    move_refs(d, LOGO_NAME_REF_COUNTS, va["logos"] - LOGOS)
    move_refs(d, LOGO_HANDLE_REF_COUNTS, va["handles"] - LOGO_HANDLES)
    if u32(d, LOGO_BOUND_AT) != LOGOS + 8 * LOGO_COUNT:
        sys.exit("unexpected logo loop bound")
    struct.pack_into("<I", d, LOGO_BOUND_AT - B, va["logos"] + 8 * len(logo_names))
    for at, old, new in STACK_PATCHES:
        patch(d, at, old, new)
    for at, old, new in COUNT_PATCHES:
        patch(d, at, old, new.format(n=f"{n:02x}"))
    at, old, new = LOGO_COUNT_PATCH
    patch(d, at, old, new.format(n=f"{len(logo_names):02x}"))

    open(out, "wb").write(d)
    print(f"wrote {out}: {n} cars, {len(logo_names)} logos, section at 0x{base:x}")


def zip_members(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename.lower(): (i.filename, z.read(i)) for i in z.infolist()}


def zip_put(path, name, payload, replace=False):
    members = zip_members(path)
    if name.lower() in members and not replace:
        print(f"{os.path.basename(path)} already has {name}")
        return
    if name.lower() in members:
        members[name.lower()] = (members[name.lower()][0], payload)
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for fname, data in members.values():
                z.writestr(fname, data)
        os.replace(tmp, path)
        print(f"replaced {name} in {os.path.relpath(path, ROOT)}")
    else:
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr(name, payload)
        print(f"added {name} to {os.path.relpath(path, ROOT)}")


def find_file(folder, name):
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    sys.exit(f"missing {name} in {folder}")


def copy_new(src, dst):
    if os.path.exists(dst):
        print(f"kept existing {os.path.relpath(dst, ROOT)}")
    else:
        shutil.copyfile(src, dst)
        print(f"created {os.path.relpath(dst, ROOT)}")


def copy_assets(spec):
    roots = {k: os.path.join(ROOT, v) for k, v in spec.get("roots", {}).items()}
    cars_dir, param_dir = os.path.join(ROOT, "cars"), os.path.join(ROOT, "param")
    for car in spec["cars"]:
        code = car["code"].lower()
        root_key, src = car["files"].split(":")
        root = roots[root_key]
        copy_new(find_file(os.path.join(root, "cars"), src + ".zip"), os.path.join(cars_dir, code + ".zip"))
        copy_new(find_file(os.path.join(root, "param"), src + "param.scr"),
                 os.path.join(param_dir, code + "param.scr"))
        hubs = zip_members(find_file(os.path.join(root, "cars"), "hubs.zip"))
        zip_put(os.path.join(cars_dir, "hubs.zip"), code + ".tga", hubs[src + ".tga"][1])
        params = zip_members(find_file(os.path.join(root, "cars"), "param.zip"))
        zip_put(os.path.join(cars_dir, "param.zip"), code + "param.dat", params[src + "param.dat"][1])

    frontend = find_file(ROOT, "frontend.zip")

    def image(ref):
        root_key, name = ref.split(":")
        return zip_members(find_file(roots[root_key], "frontend.zip"))[name.lower()][1]

    # new logos first: they may copy an image that frontend_restore then replaces
    for lg in spec.get("logos", []):
        if lg["file"].lower() not in zip_members(frontend):
            zip_put(frontend, lg["file"], image(lg["from"]))
        else:
            print(f"frontend.zip already has {lg['file']}")
    for item in spec.get("frontend_restore", []):
        data = image(item["from"])
        if zip_members(frontend)[item["file"].lower()][1] != data:
            zip_put(frontend, item["file"], data, replace=True)
        else:
            print(f"frontend.zip {item['file']} already restored")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cars", help="car list JSON (see tools/newcars.json)")
    ap.add_argument("--base", default=ORIGINAL, help="exe to copy (default TD6.exe)")
    ap.add_argument("--out", default=os.path.join(ROOT, "TD6_mod.exe"))
    args = ap.parse_args()
    if os.path.abspath(args.out) in (os.path.abspath(ORIGINAL), os.path.abspath(args.base)):
        sys.exit("refusing to overwrite the base exe")
    spec = json.load(open(args.cars))
    build_exe(spec, args.base, args.out)
    copy_assets(spec)


if __name__ == "__main__":
    main()
