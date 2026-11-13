# Task 0007: rim textures (wheel face pictures)

Test Drive 6 draws one shared 3D wheel for every car and paints a small picture of the rim on
its side. Each car has its own picture. We want better ones for our two Mercedes cars.

## Attached
- `current_190e_and_clk.png` (64x64) and `current_190e_and_clk_x4.png` (same, 4x bigger to
  look at): what both Mercedes use now (a borrowed multi-spoke rim).
- `example_impreza*.png`, `example_ferrari_f355*.png`, `example_elise*.png`: other cars' rims
  in the game, for style and layout.

## Layout (all images)
- Square, rim seen straight from the side, centred, filling the image edge to edge like the
  examples. The outer ring of the circle is the tyre: dark grey/black rubber.
- Plain black outside the circle (the corners are not seen in game).
- Final size is 64x64 pixels, so keep shapes bold: few, thick spokes, clear dark gaps between
  them. Fine detail disappears. Draw at 512x512 and also give a 64x64 version.
- No text. A tiny plain silver centre cap is fine; a simple three-pointed star on the cap is
  allowed for these two (private fan mod), nothing else.

## Wanted (PNG, names exactly as below)
1. `rim_clk500.png`: 2005 Mercedes-Benz CLK 500 (W209) style: silver 5 double-spoke
   (10 thin spokes in pairs), 17 inch look.
2. `rim_190e.png`: 1984 Mercedes-Benz 190E style: the classic flat silver "15-hole" disc
   (round holes in a ring around the centre).
3. `rim_sport5.png`: a generic silver 5-spoke sports rim we can give to future cars.

A set of generic rims for variety (future cars and traffic cars), each clearly different
from the others at 64x64:
4. `rim_mesh_gold.png`: gold cross-spoke mesh (BBS racing style), polished lip.
5. `rim_6spoke_black.png`: matte black 6-spoke Japanese racing style, thin silver lip.
6. `rim_split5_gunmetal.png`: dark gunmetal split 5-spoke (10 spokes in V pairs).
7. `rim_muscle_chrome.png`: 1970s American muscle car: chrome 5-slot, deep polished lip.
8. `rim_steel_hubcap.png`: plain painted steel wheel with a small round hubcap and vent holes
   (vans, taxis, old saloons).
9. `rim_turbofan.png`: 1980s turbine/fan style flat disc with many curved slots, silver.
10. `rim_wire.png`: classic chrome wire wheel (many thin spokes, knock-off centre), for old
    British sports cars. Keep the spokes visible at 64x64 even if simplified.
11. `rim_multispoke_silver.png`: modern silver 10-spoke, thin straight spokes.
12. `rim_offroad.png`: chunky dark grey 8-hole off-road/truck wheel, wide tyre ring.

Each in two sizes: 512x512 and 64x64 (add `_64` to the small one's name, for example
`rim_clk500_64.png`). If doing all twelve at once is too much, do 1-3 first and the rest in a
second round; same names.

## Also
Write `notes.md` with anything you are unsure about. Save everything into
`handoff/inbox/0007-rim-textures/`.
