# TD6 reverse engineering findings

Install is retail, no source. `TD6.exe` is 790528 bytes, PE32, image base 0x400000.
In `.data` and `.rdata`, file offset == RVA, so VA = 0x400000 + file offset.

Status tags: VERIFIED = checked in game or by direct parse. PARSED = read from
the exe but meaning inferred. GUESS = not checked.

## Exe layout
| Section | RVA | Raw size |
|---|---|---|
| .text | 0x1000 | 0x6c000 |
| .rdata | 0x6d000 | 0x3000 |
| .data | 0x70000 | 0x3b000 (virtual 0x1ef650, rest is BSS) |
| .rsrc | 0x260000 | 0x16000 |

## Car table (PARSED)
- 45 records, 24 bytes each, from file offset 0x81078 to 0x814b0 (45 * 24 = 0x438).
- Record: 6 x u32 = `full name ptr, short name ptr, 3-letter code ptr, class, price, packed`.
- `class` (u32): 0..3 = class 1..4. 4 = cop cars (price 0). 6 = bonus / special cars
  (Mustang GT, TVR Tuscan, Panoz AIV, both Pitbulls). Not all class 3 cars cost 500000;
  Toyota GT-One costs 1000000.
- `packed` (4 bytes): byte0 = manufacturer index (matches frontend logo set), byte1 =
  small id, byte2 = 0/1/2, byte3 = 0. Exact meaning GUESS.
- Names are in a string pool at 0x816d0..0x81d70, code strings are the zip names in `cars/`.
- Cop cars (`cp1`..`cp4`) are slots 41..44.

## Track table (PARSED)
- Records of 8 bytes: `name ptr, u16, u16`, from 0x80f68. Names include "BWD" (reverse) variants.
- Forward tracks: PARIS, NEW YORK, ROME, HONG KONG, LONDON, PELTON RACEWAY, IRELAND, ENGLAND,
  JORDAN, MAUI, LAKE TAHOE, CAPE HATTERAS, SWITZERLAND, EGYPT, NEWCASTLE, ITALY, CARIBBEAN.
- Meaning of the two u16 values not confirmed.
- Level path strings `LEVEL00\`..`LEVEL33\` at 0x88810..0x95644 (34 entries, objects/ env files).
- Loader strings: `levels\level%03d.zip`, `garage.dat`, `param\%sparam.scr`, `cars\%s.zip`,
  `himodel.dat`, `envmodel.dat`, `PlayerData\TD6.pm%01d`.

## Classes and tournaments (PARSED)
- Menu text only: 4 classes x 5 tournaments = 20 labels, pointer table at 0x82928..0x82978
  ("CLASS n TOURNAMENT m"). Names of class screens: Class1.bik..Class4.bik.
- The labels are not the definitions. Likely definitions (track lists, prize/bet tables) are
  numeric data near 0x80e0c..0x80f68. u16 runs there hold small ids with 0xff padding
  (track lists, GUESS) and money values such as 500, 2000, 2500, 3000 (GUESS).
- Game modes in the menu strings (0x80648..): quick race, single race, tournament race,
  quad race, two player cop chase, one player mission, one player cop chase, multi quad race.

## Level archives (`LEVELS/levelNNN.zip`) (VERIFIED file lists, GUESS meanings)
- 000..004: city tracks (large, models.dat ~9.6 MB, COL_nn.prr collision pieces, strip.dat,
  stripb.dat, level.mov, Levelb.mov, level0.tcl/.trf, spline1..4.td6 and spline1..4b.td6).
- 010..019, 030, 032: other tracks (same layout, fewer collision files).
- 090..095: garage / front-end scenes (`garage.dat` only).
- `b` files are the reverse direction.
- `splineN.td6`: 4 per direction, u16 pairs (racing lines or lane paths, GUESS).
- `textureNN.zip`: track textures (TGA).
- Not reversed: models.dat, strip.dat, spline format, .mov, .trf, .tcl.

## Save file (PARSED)
- `PlayerData/TD6.pm0..2`: 8940 bytes each. Header u32s then mostly zeros.
- `PlayerData/TD6,pmm`: profile index with player name strings.
- Save layout will need to change if classes or tournaments are added.

## Code analysis (capstone, static, PARSED, nothing run in a debugger)
Addresses are virtual (base 0x400000).
- Car record fields are read by code as: class = signed byte at `0x481084 + idx*24`,
  price at `0x481088`, packed bytes at `0x48108c..e`. About 40 code sites read the table.
- Car count 45 is hardcoded as `cmp reg, 0x2d` loops (class lookups): 0x41d320, 0x41d4fa,
  0x41e111, 0x41e1c9, 0x41e2b0 (cmp 0x2c), 0x41fe1a (cmp 0x2c). Other `cmp 0x2d` hits near
  0x46xxxx are the character '-' in runtime code, ignore them.
- Opponent picker at `0x41d2c0`: builds a list of every car whose class byte equals the
  tournament class, then draws 5 random picks (`mov ebx,5` loop) into the tournament record.
  So a tournament has 5 opponents + the player = 6 racers. Class 4 (cops) is mapped to
  class 2 at `0x41d4d0` in another picker.
- Tournament save state lives in BSS from `0x65bde0`: 408 bytes per class, 80 bytes per
  tournament (index = class * 408 + tournament * 80). Opponent car ids at record +0x20 (5
  bytes). Current selection (class low byte, tournament high byte) at `0x65c440`, read in 24
  places. The same record layout is written to the save file, so changing it breaks saves.
- Single-race CAR lists at `0x480e0c..0x480e70` (corrected 2026-11-12, earlier read as
  tracks): u16 car ids terminated by 0xff, 9 groups packed with no spare room. Group 1
  (0x480e0c, 15 cars) is always added; the others are added when unlock flags
  `0x65d958..0x65d95f` are set (code at 0x41400d and 0x414bc3, helper 0x413fc0 appends to
  the list at 0x65db4e, max 46 per call). The single-race track list is the byte list at
  0x480a79 (code at 0x414526).
- `0x480e70..0x480f68`: u16 money values, used by bet code at 0x412b65 (min and max bet per
  class). Exact layout not decoded.
- Tournament definitions: LOCATED, see next section.
- The `PLAYER 1`..`PLAYER 6` label table (0x4824b0) has no direct code references; it is
  probably indexed through a base pointer.
- 0x4814b0 onward is a separate table of 12-byte rows read at 0x41633f. Not decoded.
- Music table (0x479bd8) is unrelated.

## Tournament definitions (PARSED, copy logic read in code, not yet tested in game)
- Table of 20 records x 40 bytes at VA `0x480758..0x480a78` (file offset 0x80758). Record index
  n = class * 5 + tournament (class and tournament both 0-based).
- Record: byte 0 = race count (0xff = tournament does not exist), bytes 1..25 = track ids
  (max 25), +0x1c u32 = min bet, +0x20 u32 = max bet, +0x24 u32 = `k` (0, 1 or 2; looks like
  difficulty, stored at 0x65dccc when opponents are picked, meaning GUESS).
- Track id = index into the track table at 0x480f68 (0-4 cities, 5-9 city BWD, 10-19 other
  tracks, 20-29 their BWD, 30 ITALY, 31 ITALY BWD, 32 CARIBBEAN, 33 CARIBBEAN BWD). The ids
  match the `levelNNN.zip` numbers (BWD uses the `b` files in the same zip).
- Loader: new-player init at 0x41a8af copies each record into the 80-byte runtime record at
  `0x65bde0 + class*408 + tournament*80` (tracks at +0x00, count at +0x19, 0xff at +0x1c,
  opponents at +0x20, min/max bet at +0x40/+0x44, k at +0x4c). A loop at 0x41a939 counts
  per class how many records have count != 0xff (counter at 0x65bf70 + class*0x198).
- Each class has only 2 real tournaments; slots 3-5 are 0xff. Data:

| Class | T1 | T2 |
|---|---|---|
| 1 | 3 races: Pelton, Cape Hatteras, London (bet 600-2000, k0) | 4 races: England, Ireland, Egypt BWD, Rome (1000-3000, k1) |
| 2 | 6 races (2000-4000, k1) | 7 races (2500-4500, k2) |
| 3 | 10 races (6000-9500, k1) | 12 races (8000-11500, k2) |
| 4 | 14 races (12000-20000, k1) | 16 races (15000-25000, k2) |

- Implication: adding a tournament to a class is a data-only edit of a 0xff record, if the
  tournament menu draws up to 5 entries (labels for 5 exist). Existing saves keep their old
  copy of the records, so use a new player.
- Not verified: how the menu lays out tournaments 3-5, how the 'k' value changes AI.
- Tool: `tools/td6tourn.py` (tracks / list / set / clear) edits these records on a copy of the
  exe. It reproduces the hand-made test patch byte for byte and refuses to touch `TD6.exe`.
- Test patch (2026-10-23): `TD6_test.exe` is a copy of `TD6.exe` with class 1 tournament 3
  (file offset 0x807a8) set to 5 races (Paris, New York, Rome, Hong Kong, London), bet
  800-2500, k=1. Only that record changed (10 bytes). Result in game (user report): a third class 1 tournament appears in the menu, so empty
  slots 3-5 can be filled by editing data only. Not yet confirmed: that the 5 races play in
  order, or that the labels/bets show correctly.

## All-cars opponent patch (applied to `TD6_allcars.exe`, untested in game)
- Hook: file offset 0x1d309 (VA 0x41d309), original `0f be 0b 3b ca` (movsx ecx,[ebx];
  cmp ecx,edx) replaced by `e9 f7 f8 04 00` (jmp 0x46cc05).
- Cave: 39 bytes at VA 0x46cc05 (zero padding at the end of .text, section is executable).
  If the tournament slot byte at 0x65c441 is 4 (tournament 5) any car is accepted as an
  opponent except class 4 (cops); otherwise the original `cmp ecx,edx` runs. All paths
  jump back to 0x41d30e (the original `jne`).
- Player car eligibility is still class based (garage counts at 0x414ae0, entry check near
  0x41f0c6); not patched.
- Built by a scratch script from TD6.exe; class 1 tournament 5 filled with
  `td6tourn.py --exe TD6_allcars.exe set 1 5 --tracks "PELTON RACEWAY,IRELAND,ENGLAND"`.
- Menu mapping (read in code at 0x41efc0 and 0x41f233): the tournament menu has one entry per
  used slot (count at 0x65bf70 + class*0x198, computed when the player is created) and the
  chosen entry index is stored directly as the slot (0x65c441). So slots must be filled in
  order. With only slots 1, 2 and 5 filled the menu shows 3 entries and entry 3 loads the
  empty slot 3, so slot 5 is unreachable. Fix: fill slots 3 and 4 too (done in
  `TD6_allcars.exe`; the tool now warns about gaps). The count is stored in the save, so a
  player created before the change must be recreated.

## Adding a 46th car (research 2026-11-12, static only, nothing patched)
Car ids are stored as single bytes everywhere found (garage, opponents, dealer list), so a
46th car (id 45) does not change the save layout. What has to change:
1. Car table (45 x 24 bytes at 0x481078) has no room after it. Move it (plus the new record)
   to a new PE section and repoint the 42 code references (list below). There is room in the
   PE header for a 5th section header; CheckSum is 0; SizeOfImage is 0x276000.
2. Paint table at 0x4814b0: 45 rows x 3 dwords, one dword per paint choice (low u16 = body
   tint, high u16 = second tint for stripes on some cars). 14 code refs, including two fixed
   reads at 0x41a955 (row 27 ELI) and 0x41a985 (row 12 CHR) for default car picks. Move it too.
3. Hardcoded car count 45 (`cmp ..., 0x2d`): 0x41d320, 0x41d4fa (opponent pickers),
   0x41e111 (dealer list by class), 0x41e1c9 (cop car list). End pointer 0x4814c0
   (= 0x481088 + 45*24) at 0x41a813 (per-class price range loop). Other 0x2c/0x2d/0x2e
   immediates checked: UI coordinates, key codes, track-list length, not car related.
4. Single-race car lists (0x480e0c) are packed tight: move group 1 with the new id added and
   repoint 0x41400d and 0x414bc3 (and their loop bound 0x480e68).
5. Fixed-size lists that limit growth: dealer list per class at 0x65d988 (20 x 16 bytes),
   garage at 0x65c49c (20 x 16 bytes, byte 0 = car id, 0xff = empty). Classes have 12, 9, 7
   and 8 cars now, so one more fits.
6. Packed byte 0 (record +20) = manufacturer index into 19 logo slots (0x65b440, count 0x13
   at 0x42364b): reuse an existing brand or add a 20th (not researched). Packed byte 1
   (+21) = engine sound index into the name table at 0x49a7f8. Packed byte 2 (+22) is
   compared with 2 at 0x4153bc/0x415ddd/0x4178bd/0x417933 (meaning unknown).
7. Assets by code string: `cars\<code>.zip` (himodel.dat, envmodel.dat, carbody.tga),
   `param\<code>param.scr`, hub texture `<code>.tga` inside `cars\hubs.zip`.
8. Not yet checked: any loop over cars that stops on a sentinel instead of a count, replay
   files, text widths of new names. A cloned test car (copy of an existing car under a new
   code) should be tried in game before the Mercedes.

Built 2026-11-12 (untested in game): `tools/td6addcar.py mcc eli --name "MERC TEST" --full
"MERCEDES TEST CAR" --class 1 --price 30000` wrote `TD6_newcar.exe` (new section `.td6mod`
at VA 0x676000, file offset 0xc1000: car table +0x000, paint table +0x460, car list 1
+0x690, strings +0x700) and the clone files `cars/mcc.zip`, `param/mccparam.scr`,
`mcc.tga` in `cars/hubs.zip`, `mccparam.dat` in `cars/param.zip`. Disassembly check: no
references to the old tables remain in .text, all count checks read 0x2e.
First run crashed (access violation at 0x41633f): the front end reads the paint table with
the dealer-list id 0xff of empty slots (`rand()%3 + id*3`, the validity check 0x401a50
always returns 1). The original reads harmless data after the table; the 4 KB section ended
before row 255. Fixed by giving the car and paint tables room for 256 ids (section 0x3000:
cars +0x0000, paint +0x1800, list +0x2400, strings +0x2440). Rule: any moved per-car table
needs room for index 255.
Second run crashed at 0x4183d9: missed per-car table, car info text (12 string pointers per
car, 45 x 48 bytes at 0x4724d8, one code ref 0x4183c4; lines: title, blank, ENGINE, value,
BHP, value, 0-60, value, TOP SPEED, value, LATERAL ACCELERATION, value; first char is the
colour, `y` yellow, `w` white). Moved into the section at +0x3000 (256 x 48 bytes, section
now 0xF000). Searches run for other per-car tables: x3-stride indexing near data tables,
pointer runs of length 45*k in .data, data tables indexed right after loading a car id from
the dealer/garage/showroom/single-race lists. Only this one was found.
Third build: user reports it works in game (2026-11-12). Details not yet confirmed one by
one: dealer listing, purchase, race, single-race list, opponent picks.

Car table code refs (VA): 414b08 4153bc 415b2a 415ddd 4163aa 416499 41655b 4165a9 416811
4168ae 4176cf 4178bd 417933 419d04 41a7cb 41a87f 41d304 41d4c5 41d4de 41e0e5 41e17c 41e3d6
41e43a 41f183 420b65 421443 421c4b 42363e 4236f7 4244ec 42457a 424708 424785 42619c 42a3d4
43618a 459efe 459f5f 45b914 45b973 45ba2e 45ba9b.
Paint table code refs (VA): 41633f 41a813 41a955 41a985 41d69b 41da4a 41dae3 41db80 41dc19
41dca9 41dd6c 41de61 41df22 41e1b0.

## Car model conventions (PARSED from retail cars, used by tools/blender_car.py)
- Game axes: +X right, +Y up, +Z nose (left-handed). Lights in .scr confirm: HEAD_LIGHTS at
  +Z, CAR_LIGHTS (tail) at -Z.
- Models are centred on their bounding box (y range is symmetric, e.g. eli -173..173).
- Triangle order: for every retail triangle, cross(b-a, c-a) points against the stored
  outward normal. Blender's outward CCW order maps to this when converting with a mirror.
- Scale: wheel arch radius in the model is about 0.7 x WHEEL_RADIUS (eli 126-131 vs 160,
  att 110-115 vs 165, jag 119-121 vs 180). Wheel centre sits about 45-60 units above the
  body bottom. Wheelbase of sedans about 850-950 units.
- envmodel.dat is a low-detail copy (about half the triangles, same layout as himodel).
- CORNER_POS, BOUND_SPHERE and RIDE_HEIGHT are almost the same on every car (generic box).

## Mercedes C230 (car 46, code mcc), built 2026-11-12, untested in game
- Source: handoff/inbox/0002-mercedes-c230-source (Sketchfab, Efe Metin, CC-BY-4.0).
- tools/blender_car.py: wheels removed (2544 of 3588 triangles were wheels), body reduced to
  560 triangles (hi) and 300 (env), scale 315 game units per model unit, nose -Y in the
  glTF. Texture: the model's own 512x512 atlas scaled to 256x256 (silver, not the yellow
  paint mask, so the paint tint may not apply).
- param/mccparam.scr: Elise handling; WHEEL_CENTRES from the model ({+-261,-168,503} front,
  {+-261,-168,-442} rear), WHEEL_RADIUS 165, lights estimated, BOUND_SPHERE 900, corner box
  z +-780 (car is 1586 long).
- TD6_newcar.exe rebuilt: "MERCEDES C230" / "2001 MERCEDES-BENZ C230", class 1, 31000. Brand
  logo and engine sound still the Elise's (Lotus).

## Racer count
- Also hardcoded: `0x4142c0` initialises 6 grid positions (`cmp ax, 6`), `0x4143c0` fills 6
  prize amounts (100..600, tables at 0x65bcf8 and 0x65dad2). Mode 8 uses 2 or 4 racers.
- 6 racers = 5 random opponents (loop count 5 at 0x41d331) + the player. The per-tournament
  record only has room for 5 opponent bytes, and per-race arrays are not yet audited.
  Raising it means: new record layout (and save format), the picker loop, and every
  per-racer array and start grid in the race code. Large job, not located fully.

## Feasibility (current view)
| Goal | Route | State |
|---|---|---|
| New car, existing slot | data only (`tools/td6car.py`) | VERIFIED |
| New car, new slot | patch car table + count in exe (24-byte stride, other data starts right at 0x814b0, so the table would have to be moved and every reference to it patched) | not tried |
| Class 5 | `class` value 4 is used by cops; pickers filter by class and the menu has 4 class screens, 4 x 408-byte save blocks | not tried |
| All-cars tournament | opponent picker (0x41d2c0) filters cars by class: patching the `cmp ecx, edx` / `jne` at 0x41d30c to always match would let any car be an opponent. The track list part is data only: fill a 0xff record (see Tournament definitions) | not tried |
| New tracks | data format not reversed; also needs a track table slot | not tried |
| More upgrades | not located | not tried |
| 7+ racers | needs code analysis | not tried |

## Remaster mod (Allef Almeida, 2019) - compared 2026-11-12
Source: `Test_Drive_6_Remastered.rar`; changed files extracted to `handoff/inbox/0004-remaster-2019/`.
- Changed: all 42 `Cars/*.zip`, `hubs.zip`, `Cars/sound.zip` (0.5 MB -> 3.2 MB), `Param/*.scr`,
  6 wavs in `Sound/Sound.zip`, 8 tgas in `Static.zip` (speedo, dials, envmap 256x256), 1 logo in `Frontend.zip`, the exe.
- Unchanged (1999 files): Levels, track textures, Sky, Traffic, Loading, Movies, Music, Objects.
- Car models (converted from NFS High Stakes / Hot Pursuit 2): 800-21,000 triangles (retail 310-620).
  So the engine takes 20,000+ triangle cars with no code change. `envmodel.dat` = copy of `himodel.dat`.
  `carbody.tga` is still 256x256.
- Exe: same build as retail (same timestamp, `.text` identical except below). `.rsrc` grew 0x2000,
  so file size is 798720 and a new section would start at VA 0x678000 / file 0xc3000.
  Car table still at 0x481078: only names changed (10 cars swapped for other makes, e.g. ATL = Ferrari F355, 400 = F40).
  `TD6 - BMW & McLaren.exe` also swaps codes VAN<->BMW and TOY<->MCL.
- It adds 24 bytes of code at 0x46cc05 (a strlen). Same address as our all-cars cave: move ours if combining.

## Remaster adopted as the base (2026-11-12)
The remaster's cars, params, sounds, `frontend.zip` and `static.zip` now sit in the main folder
(user tested both remaster exes: OK). Restore point with the retail-based state: commit `52bf66d`.
- `TD6.exe` stays retail (untouched). `TD6_remaster.exe` / `TD6_remaster_bmw.exe` = the remaster's exes.
- `TD6_mod.exe` = `TD6_remaster.exe` + 46th car (C230), built with
  `td6addcar.py ... --base TD6_remaster.exe --out TD6_mod.exe` (section lands at VA 0x678000, file 0xc3000).
  The remaster exe has stray tool tags in the header padding (0x2b0 "SUN/CLS", 0xfd4); harmless.
- `TD6_test.exe`, `TD6_allcars.exe`, `TD6_newcar.exe` are retail-based: with the remaster files their
  car names no longer match the models. Rebuild on the remaster base before using them.
- `cars/hubs.zip` = remaster hubs + `180.tga`, `tus.tga`, `mcc.tga` kept from ours. `cars/param.zip` kept (ours).
- `param/mccparam.scr` still has retail Elise handling; the other cars use the remaster's handling model.

### Cars the remaster replaced (to add back later as extra slots)
Retail models/params: `git show 52bf66d:cars/<code>.zip` (or `C:\MagiPacks\Test Drive 6\cars`).
To re-add one: copy its retail zip + param under a new 3-letter code, then add a slot (td6addcar
handles 1 extra car today; needs multi-car support).
| Code | Retail car (removed) | Remaster car (now in the slot) |
|---|---|---|
| mam | 1999 Marcos Mantaray | BMW Z3 Roadster |
| atl | 1999 Venturi Atlantique | Ferrari F355 Berlinetta |
| 400 | 1999 Venturi 400GT | Ferrari F40 |
| grf | 1999 TVR Griffith | TVR Tuscan Speed 6 |
| chd | Dodge Concept | Dodge Intrepid |
| sup | 1997 Ford Mustang Super Stallion | Ford Mustang GT |
| mgt | 1999 Ford Mustang Saleen S351 | Ford Mustang SVT Cobra R |
| van | Aston Martin Project Vantage | Aston Martin V12 Vanquish |
| s12 | 1999 TVR Speed 12 | TVR Cerbera Speed 12 |
| cud | 1972 Plymouth Hemi Cuda | Plymouth Cuda '70 |
| sub | 1999 Subaru Impreza 22B STi | Subaru Impreza GT Prodrive |
| cp1 | Jaguar police car | Police Paseo |
| cp2 | Dodge Charger police car | Police Camaro |
| cp3 | Ford Mustang police car | Police Diablo |
| cp4 | TVR Cerbera police car | Police Corvette |

Also replaced: the user's own edits (lit = aud model, sky.zip, skyparam.scr, attparam.scr); they are in `52bf66d`.
Only in `TD6_remaster_bmw.exe`: BMW V12 LMR (`bmw.zip`) takes the van slot and McLaren F1 GTR (`mcl.zip`)
the toy slot. Better plan: add both as new slots so the Vanquish and GT-One stay.

## Limits for adding many cars (static, 2026-11-12, remaster exe = same code)
- Opponent picker 0x41d2c0: per-class candidate list is a 48-byte stack buffer (esp+0x14 in a
  0x34 frame), so max 48 cars per class.
- Dealer list 0x65d988 and garage 0x65c49c: 20 slots per class.
- Single-race list: count word 0x65db4e, entries from 0x65db50, next variable at 0x65dbac,
  so max 46 entries in total over all unlocked groups (retail groups hold 41 ids). Not in the
  save block. Refs: 0x65db4e x40, 0x65db50 x4 (0x4141a8, 0x414d58, 0x41d9f6, 0x42362e).
  Helper 0x413fc0 copies max 0x2e ids per group; group 1 loop bound is 0x480e68 (46 ids).
- `cmp eax, 0x2c` at 0x41e2b0 and 0x41fe1a compare menu/key codes, not the car count.
- Count immediates are imm8/imm16: `push imm8` and `cmp r16, imm8` (sign-extended), so up to
  127 cars without changing instruction sizes.

## 13 more cars + 20th logo (built 2026-11-12; user reports it works in game)
`python tools/td6addcar.py tools/newcars.json --base TD6_remaster.exe --out TD6_mod.exe`
builds 59 cars: ids 45 mcc, 46-56 the retail cars the remaster replaced (records, paint, spec
text and files from the retail backup, new codes mar c72 vat gri dco sst 22b v40 sal pva ts2),
57 lmr (BMW V12 LMR) and 58 f1g (McLaren F1 GTR), both from `TD6_remaster_bmw.exe` + remaster files.
Cars per class: 15, 14, 9, 12. Ids must only be appended (saves store them).
Found while doing it:
- Single race list is sorted through a display order list at 0x472020 (u16 ids, 0xff end,
  max 45; refs 0x41418d/0x414d3d, bounds 0x4141c4/0x414d81). Cars missing from it are dropped,
  so the C230 never showed in single race before this build. Sorting uses a 0x5c stack buffer
  (`sub esp,0x5c` at 0x414000 and 0x414b35, `mov ecx,0x17` + `rep movsd` back into 0x65db4e).
  Patched to 0x7c / 0x1f (max 61 entries); both functions have no other stack locals or args.
- Logos: 19 x (name ptr, 0) at 0x481f50, loaded by 0x4235d0 as `<name>.tga` from frontend.zip
  into u16 handles at 0x65b440 (0x65b468 is used elsewhere). Count `mov edx,0x13` at 0x42364b,
  bound `cmp esi,0x481fe8` at 0x423608. Table, handles and count moved/raised for a 20th logo
  FERRARI (`ferrari.tga` = the remaster's Ferrari image); `venturi.tga` restored from retail.
  BMW (12) and McLAREN (17) logos already existed (retail cut cars).
- Logo fixes on remaster cars: mam (Z3) -> BMW, mgt (Cobra R) -> FORD, atl/400 -> FERRARI.
- Section `.td6mod` is now 0x10000: cars +0, paint +0x1800, group 1 +0x2400, order +0x2480,
  race buffer +0x2500, logo names +0x2600, logo handles +0x2700, text +0x3000, strings +0x6000.
- Capstone sweep of .text: no operand left on any moved table.

## ChatGPT-built C230 (handoff 0005, 2026-11-12): rejected
A procedural 3,556-triangle model from ChatGPT (flat front/back, painted details, yellow mask)
imported fine (winding, scale 320 units/m, wheels) but looked terrible in game; reverted to the
Sketchfab-based model. Use ChatGPT for 2D art only; take car meshes from real 3D models.
Scale reference from remaster cars: about 320 game units per metre (Impreza, DB7).

## Mercedes 190E (car 59) + Mercedes logo (built 2026-11-12; works in game after the TGA fix)
- Model: "1984 Mercedes 190E" by Dave Love (Sketchfab, CC-BY-4.0, credit required), from
  handoff/inbox/0003. Converted with the extended `tools/blender_car.py` (scale 320/m,
  wheels from EXT_Tyre, interior/engine/wheels dropped, 14,000 / 7,638 triangles, flat
  colour atlas with the paint mask; only the plates keep texture detail):
  `--wheel-material EXT_Tyre --drop "INT_,ENG_,Material_109,EXT_Rim,EXT_Calipers,EXT_Brake,EXT_Badges"
   --keep INT_Glass_Refl --hi 14000 --env 5000 --bake 256 --detail Plate_D --paint EXT_Car_Paint
   --colour "EXT_Glass=30,38,48;INT_Glass_Refl=30,38,48;HL_Glass=200,205,210;EXT_Chrome=205,208,212"`
- Slot 19e: record from eli (I4 engine sound), handling/hub from xkr, class 1, 30,000.
- Logo 21 MERCEDES: `mercedes.tga` (60x40, 32-bit, alpha, bottom-up like the others) drawn
  by a script and added to frontend.zip; used by mcc and 19e.
- Logo TGAs: 60x40, descriptor 8, background alpha 0.
- C230 model credit: Efe Metin (Sketchfab, CC-BY-4.0).
- First 190E test (2026-11-12): whole car black, paint had no effect. Cause: carbody.tga row
  order. Retail textures are top-down (TGA descriptor 0x20), the remaster's bottom-up (0x08),
  and the game honours the flag (checked: remaster sky/cp2 rear faces sample their red tail
  light patch only with the flag honoured). td6car.py ignored it, so importing into a slot
  copied from a remaster car (19e <- xkr) stored the image upside down. Fixed: read_tga
  returns top-first rows, import writes in the car's own order. 190E texture re-imported.

## Paint tint rule (tint routine 0x431200, read 2026-11-12)
Called from the front end (0x4169ce) and the race loader (0x45a210) with two colours (body,
stripe) from the paint table. Per pixel (R, G, B):
- B == 0 and (R or G) > 0  -> body colour * (R + G) / 2 / 255   (the yellow mask; red with B 0 too!)
- R == 0 and (G or B) > 0  -> stripe colour * (G + B) / 2 / 255 (cyan mask, e.g. Viper stripes)
- anything else, and pure black, keeps its colour.
So unpainted parts need B >= 1 and R >= 1: the remaster keeps a little blue in its tail lights
(Impreza 160,0,16). The 190E's pure red/orange lights (B = 0) were painted; blender_car.py now
clamps R and B to >= 1 outside the paint squares (`protect_colours`). 190E texture rebuilt; user confirms the lights keep their colours.
