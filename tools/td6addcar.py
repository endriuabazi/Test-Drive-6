"""Add a 46th car to Test Drive 6 (writes a COPY of TD6.exe plus new asset files).

Usage (run from the game folder):
  python tools/td6addcar.py mcc eli --name "MERC TEST" --full "MERCEDES TEST CAR" \
      --class 1 --price 30000 --out TD6_newcar.exe

  code     3-letter code of the new car (new files: cars/<code>.zip, param/<code>param.scr,
           <code>.tga in cars/hubs.zip, <code>param.dat in cars/param.zip)
  clone    existing car whose record, paint colours and files are copied
  --class  1-4 (default: same as the clone)   --price  (default: same as the clone)

What the exe copy gets (see tools/FINDINGS.md, "Adding a 46th car"):
  - a new section .td6mod holding the car table (46 records), the paint table (46 rows),
    the car info text table (46 x 12 lines), single-race car list 1 with the new car
    appended, and the new name strings
  - the 42 car table, 14 paint table and 1 text table code references repointed
  - the hardcoded car count 45 raised to 46 (4 loops, 1 log call, 1 end pointer)
TD6.exe itself is never modified. Existing asset files are only extended (zip members added).
"""
import argparse
import os
import shutil
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.path.join(ROOT, "TD6.exe")
B = 0x400000

CARS, REC = 45, 24
CAR_TABLE, PAINT, PAINT_ROW = 0x481078, 0x4814B0, 12
LIST1, LIST1_BOUND = 0x480E0C, 0x480E68

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
# (address, original bytes, patched bytes): car count 45 -> 46
COUNT_PATCHES = [
    (0x41D320, "663d2d00", "663d2e00"),
    (0x41D4FA, "663d2d00", "663d2e00"),
    (0x41D500, "6a2d", "6a2e"),
    (0x41E111, "6683f92d", "6683f92e"),
    (0x41E1C9, "6683fb2d", "6683fb2e"),
]

# layout of the new section. The game reads the tables with unchecked byte ids, including
# 0xff for empty dealer slots (0x41633f), so each table gets room for all 256 ids; reads
# past the end of the section crash, while the original reads harmless data after the table.
SEC_SIZE = 0xF000
OFF_CARS, OFF_PAINT, OFF_LIST, OFF_STR, OFF_TEXT = 0x0000, 0x1800, 0x2400, 0x2440, 0x3000
assert OFF_CARS + 256 * 24 <= OFF_PAINT and OFF_PAINT + 256 * 12 <= OFF_LIST
assert OFF_TEXT + 256 * TEXT_LINES * 4 <= SEC_SIZE


def rd(d, va, n=4):
    return bytes(d[va - B:va - B + n])


def u32(d, va):
    return struct.unpack_from("<I", d, va - B)[0]


def cstr(d, va):
    o = va - B
    return bytes(d[o:d.index(b"\0", o)]).decode("latin1")


def repoint(d, ins, lo, hi, new_of):
    """Replace the one imm32/disp32 in [lo, hi) inside the instruction at ins."""
    window = rd(d, ins, 12)
    hits = [i for i in range(9) if lo <= struct.unpack_from("<I", window, i)[0] < hi]
    if len(hits) != 1:
        sys.exit(f"unexpected bytes at 0x{ins:x}: {window.hex()}")
    old = struct.unpack_from("<I", window, hits[0])[0]
    struct.pack_into("<I", d, ins - B + hits[0], new_of(old))


def add_section(d, name, size):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = pe + 24
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    hdr = opt + struct.unpack_from("<H", d, pe + 20)[0] + nsec * 40
    if any(d[hdr:hdr + 40]):
        sys.exit("no room for a new section header")
    va = struct.unpack_from("<I", d, opt + 56)[0]      # SizeOfImage, already page aligned
    raw = len(d)
    struct.pack_into("<8sIIIIIIHHI", d, hdr, name, size, va, size, raw, 0, 0, 0, 0, 0xC0000040)
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    struct.pack_into("<I", d, opt + 56, va + size)
    d.extend(bytes(size))
    return B + va, raw


# rd/u32/cstr/repoint use file offset == VA - base, true for the original sections only


def build_exe(args):
    d = bytearray(open(ORIGINAL, "rb").read())
    codes = [cstr(d, u32(d, CAR_TABLE + i * REC + 8)).lower() for i in range(CARS)]
    if args.code in codes:
        sys.exit(f"{args.code} is already one of the 45 cars")
    if args.clone not in codes:
        sys.exit(f"unknown clone car {args.clone}")
    src = codes.index(args.clone)

    base, sec = add_section(d, b".td6mod", SEC_SIZE)  # VA for pointers, file offset for writes
    cars, paint, lst, strs = base + OFF_CARS, base + OFF_PAINT, base + OFF_LIST, base + OFF_STR

    # strings
    pool, ptrs = bytearray(), []
    for s in (args.full, args.name, args.code.upper(), "y" + args.full):
        ptrs.append(strs + len(pool))
        pool += s.encode("latin1") + b"\0"
    if OFF_STR + len(pool) > SEC_SIZE:
        sys.exit("names too long")
    d[sec + OFF_STR:sec + OFF_STR + len(pool)] = pool

    # car table + new record
    old_cars = rd(d, CAR_TABLE, CARS * REC)
    d[sec + OFF_CARS:sec + OFF_CARS + CARS * REC] = old_cars
    rec = bytearray(old_cars[src * REC:(src + 1) * REC])
    cls, price = struct.unpack_from("<II", rec, 12)
    cls = cls if args.cls is None else args.cls - 1
    price = price if args.price is None else args.price
    struct.pack_into("<IIIII", rec, 0, ptrs[0], ptrs[1], ptrs[2], cls, price)
    d[sec + OFF_CARS + CARS * REC:sec + OFF_CARS + (CARS + 1) * REC] = rec

    # paint table + new row
    old_paint = rd(d, PAINT, CARS * PAINT_ROW)
    d[sec + OFF_PAINT:sec + OFF_PAINT + CARS * PAINT_ROW] = old_paint
    d[sec + OFF_PAINT + CARS * PAINT_ROW:sec + OFF_PAINT + (CARS + 1) * PAINT_ROW] = \
        old_paint[src * PAINT_ROW:(src + 1) * PAINT_ROW]

    # single-race car list 1 + new id
    ids, va = [], LIST1
    while (v := struct.unpack_from("<H", d, va - B)[0]) != 0xFF:
        ids.append(v)
        va += 2
    ids += [CARS, 0xFF]
    struct.pack_into(f"<{len(ids)}H", d, sec + OFF_LIST, *ids)

    # car info text table + new entry: title line = "y" (yellow) + full name, rest from clone
    row = TEXT_LINES * 4
    old_text = rd(d, TEXT, CARS * row)
    text = base + OFF_TEXT
    d[sec + OFF_TEXT:sec + OFF_TEXT + CARS * row] = old_text
    entry = bytearray(old_text[src * row:(src + 1) * row])
    struct.pack_into("<I", entry, 0, ptrs[3])
    d[sec + OFF_TEXT + CARS * row:sec + OFF_TEXT + (CARS + 1) * row] = entry
    repoint(d, TEXT_REF, TEXT, TEXT + CARS * row, lambda old: text + old - TEXT)

    # code references
    if len(CAR_REFS) != 42 or len(PAINT_REFS) != 13:
        sys.exit("reference lists damaged")
    car_end = CAR_TABLE + CARS * REC
    for ins in CAR_REFS:
        repoint(d, ins, CAR_TABLE, car_end, lambda old: cars + old - CAR_TABLE)
    for ins in PAINT_REFS:
        repoint(d, ins, PAINT, PAINT + CARS * PAINT_ROW, lambda old: paint + old - PAINT)
    repoint(d, CAR_END_REF, car_end + 16, car_end + 17, lambda old: cars + (CARS + 1) * REC + 16)
    for ref in LIST_REFS:
        repoint(d, ref - 1, LIST1, LIST1 + 1, lambda old: lst)
    for ref in BOUND_REFS:
        repoint(d, ref - 1, LIST1_BOUND, LIST1_BOUND + 1, lambda old: lst + LIST1_BOUND - LIST1)
    for va, old, new in COUNT_PATCHES:
        if rd(d, va, len(old) // 2).hex() != old:
            sys.exit(f"unexpected bytes at 0x{va:x}")
        d[va - B:va - B + len(new) // 2] = bytes.fromhex(new)

    open(args.out, "wb").write(d)
    print(f"wrote {args.out}: car {CARS} = {args.code} (clone of {args.clone}), class {cls + 1}, "
          f"price {price}, section at 0x{base:x}")


def add_member(path, name, payload):
    with zipfile.ZipFile(path) as z:
        if name.lower() in (n.lower() for n in z.namelist()):
            print(f"{os.path.basename(path)} already has {name}")
            return
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, payload)
    print(f"added {name} to {os.path.relpath(path, ROOT)}")


def copy_new(src, dst):
    if os.path.exists(dst):
        print(f"kept existing {os.path.relpath(dst, ROOT)}")
    else:
        shutil.copyfile(src, dst)
        print(f"created {os.path.relpath(dst, ROOT)}")


def clone_assets(code, clone):
    copy_new(os.path.join(ROOT, "cars", clone + ".zip"), os.path.join(ROOT, "cars", code + ".zip"))
    copy_new(os.path.join(ROOT, "param", clone + "param.scr"),
             os.path.join(ROOT, "param", code + "param.scr"))
    hubs = os.path.join(ROOT, "cars", "hubs.zip")
    add_member(hubs, code + ".tga", zipfile.ZipFile(hubs).read(clone + ".tga"))
    params = os.path.join(ROOT, "cars", "param.zip")
    add_member(params, code + "param.dat", zipfile.ZipFile(params).read(clone + "param.dat"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("clone")
    ap.add_argument("--name", required=True, help="short name (menus)")
    ap.add_argument("--full", required=True, help="full name (details screen)")
    ap.add_argument("--class", type=int, dest="cls", choices=range(1, 5))
    ap.add_argument("--price", type=int)
    ap.add_argument("--out", default=os.path.join(ROOT, "TD6_newcar.exe"))
    args = ap.parse_args()
    args.code, args.clone = args.code.lower(), args.clone.lower()
    if len(args.code) != 3 or not args.code.isalnum():
        sys.exit("code must be 3 letters or digits")
    if os.path.abspath(args.out) == os.path.abspath(ORIGINAL):
        sys.exit("refusing to overwrite TD6.exe")
    build_exe(args)
    clone_assets(args.code, args.clone)


if __name__ == "__main__":
    main()
