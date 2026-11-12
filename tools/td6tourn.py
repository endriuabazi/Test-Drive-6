"""Edit Test Drive 6 tournament records in a COPY of TD6.exe.

Usage (run from the game folder):
  python tools/td6tourn.py tracks                 # track ids and names
  python tools/td6tourn.py list                   # all 20 tournament slots
  python tools/td6tourn.py set 1 3 --tracks "PARIS,ROME BWD,10,LONDON" --min 800 --max 2500 --k 1
  python tools/td6tourn.py clear 1 3              # make the slot empty again

Class is 1-4, tournament is 1-5. --tracks takes ids or track names (as printed by
`tracks`), comma separated, up to 25. On an empty slot --min/--max/--k default to the
values of tournament 1 of the same class. On a used slot, omitted fields are kept.

The tool only writes to a copy (default TD6_test.exe, made from TD6.exe on first use).
Records are 40 bytes at file offset 0x80758: byte 0 race count (0xff = no tournament),
bytes 1-25 track ids, then u32 min bet, u32 max bet, u32 k at +28/+32/+36.
New tournaments show up for new players only; existing saves keep their old copy.
Fill slots in order (1, 2, 3...): the menu shows one entry per used slot and entry n
loads slot n, so a gap makes the last entries load empty records.
"""
import argparse
import os
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.path.join(ROOT, "TD6.exe")
DEFAULT_COPY = os.path.join(ROOT, "TD6_test.exe")

IMAGE_BASE = 0x400000
RECORDS = 0x80758
RECORD_SIZE = 40
MAX_TRACKS = 25
EMPTY = 0xFF
TRACK_TABLE = 0x80F68
TRACK_COUNT = 34
CLASSES, SLOTS = 4, 5


def load_tracks(data):
    names = []
    for i in range(TRACK_COUNT):
        ptr = struct.unpack_from("<I", data, TRACK_TABLE + i * 8)[0] - IMAGE_BASE
        if not 0 < ptr < len(data):
            sys.exit(f"track table not found at 0x{TRACK_TABLE:x}: is this a TD6.exe?")
        names.append(data[ptr:data.index(b"\0", ptr)].decode("ascii"))
    return names


def parse_tracks(text, names):
    by_name = {n.upper(): i for i, n in enumerate(names)}
    ids = []
    for part in text.split(","):
        part = part.strip()
        if part.isdigit() and int(part) < len(names):
            ids.append(int(part))
        elif part.upper() in by_name:
            ids.append(by_name[part.upper()])
        else:
            sys.exit(f"unknown track '{part}' (run `tracks` for ids and names)")
    if not 1 <= len(ids) <= MAX_TRACKS:
        sys.exit(f"a tournament needs 1-{MAX_TRACKS} tracks, got {len(ids)}")
    return ids


def offset(cls, tour):
    if not (1 <= cls <= CLASSES and 1 <= tour <= SLOTS):
        sys.exit(f"class must be 1-{CLASSES} and tournament 1-{SLOTS}")
    return RECORDS + ((cls - 1) * SLOTS + tour - 1) * RECORD_SIZE


def read_record(data, off):
    count = data[off]
    if count == EMPTY:
        return None
    tracks = list(data[off + 1:off + 1 + count])
    low, high, k = struct.unpack_from("<III", data, off + 28)
    return tracks, low, high, k


def describe(rec, names):
    if rec is None:
        return "empty"
    tracks, low, high, k = rec
    return (f"{len(tracks)} races, bet {low}-{high}, k={k}: "
            + ", ".join(names[t] if t < len(names) else f"?{t}" for t in tracks))


def target(path):
    path = os.path.abspath(path)
    if path == os.path.abspath(ORIGINAL):
        sys.exit("refusing to edit the original TD6.exe, use a copy")
    if not os.path.exists(path):
        shutil.copyfile(ORIGINAL, path)
        print(f"created {path} from TD6.exe")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exe", default=DEFAULT_COPY, help="exe copy to read/edit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tracks")
    sub.add_parser("list")
    p = sub.add_parser("set")
    p.add_argument("cls", type=int)
    p.add_argument("tour", type=int)
    p.add_argument("--tracks")
    p.add_argument("--min", type=int, dest="low")
    p.add_argument("--max", type=int, dest="high")
    p.add_argument("--k", type=int)
    p = sub.add_parser("clear")
    p.add_argument("cls", type=int)
    p.add_argument("tour", type=int)
    args = ap.parse_args()

    path = target(args.exe) if args.cmd in ("set", "clear") else (
        args.exe if os.path.exists(args.exe) else ORIGINAL)
    data = bytearray(open(path, "rb").read())
    names = load_tracks(data)

    if args.cmd == "tracks":
        for i, n in enumerate(names):
            print(f"{i:2d}  {n}")
        return
    if args.cmd == "list":
        print(f"({os.path.basename(path)})")
        for c in range(1, CLASSES + 1):
            for t in range(1, SLOTS + 1):
                rec = read_record(data, offset(c, t))
                print(f"class {c} tournament {t}: {describe(rec, names)}")
        return

    off = offset(args.cls, args.tour)
    if args.cmd == "clear":
        data[off:off + RECORD_SIZE] = bytes([EMPTY]) + bytes(RECORD_SIZE - 1)
    else:
        cur = read_record(data, off)
        if cur is None:
            if not args.tracks:
                sys.exit("slot is empty, --tracks is required")
            base = read_record(data, offset(args.cls, 1))
            tracks, low, high, k = [], *(base[1:] if base else (1000, 3000, 1))
        else:
            tracks, low, high, k = cur
        if args.tracks:
            tracks = parse_tracks(args.tracks, names)
        low = low if args.low is None else args.low
        high = high if args.high is None else args.high
        k = k if args.k is None else args.k
        if low > high:
            sys.exit("--min must not exceed --max")
        rec = bytearray(RECORD_SIZE)
        rec[0] = len(tracks)
        rec[1:1 + len(tracks)] = bytes(tracks)
        struct.pack_into("<III", rec, 28, low, high, k)
        data[off:off + RECORD_SIZE] = rec
    open(path, "wb").write(data)
    print(f"class {args.cls} tournament {args.tour}: "
          f"{describe(read_record(data, off), names)}")
    used = [read_record(data, offset(args.cls, t)) is not None for t in range(1, SLOTS + 1)]
    if used != sorted(used, reverse=True):
        print("warning: empty slot before a used one. The menu lists as many entries as there "
              "are used slots and maps entry n to slot n, so fill slots in order.")


if __name__ == "__main__":
    main()
