# Task 0008: new dashboard gauge (rev counter) and digit fonts

The in-race dashboard is drawn from small images. The game draws the needle itself and
rotates it over the dial picture, so the new dial must keep the scale in exactly the same
place.

## Attached (current game images, PNG with transparency)
- `speedo.png` (128x128): the rev counter dial face, 0-8 (x1000 rpm), red zone 7-8. Only the
  lower-left quarter of the circle shows here because the game shows part of it on screen.
- `dialnum.png` (160x28): digits 0-9 for the digital speed readout, each 16x28.
- `gears.png` (192x40): gear display R, N, 1-6, each 24x40, red LCD style.
- `kph.png`, `mph.png` (24x16): unit labels.

## Wanted (PNG with transparency, same sizes and names, drawn larger first if you like)
1. `speedo.png`: a modern, clean sports-car rev counter. KEEP: same 128x128 canvas, same
   circle centre and radius, the numbers 0-8 and their tick marks at exactly the same angles
   as the original (lay your design over the original to check), red zone from 7 to 8,
   transparent where the original is transparent. Free: colours, fonts, glow, background
   texture. Dark face with white or light-blue markings reads best in game.
2. `dialnum.png`: matching digits 0-9, same 160x28 strip, each digit centred in its own
   16-pixel cell, transparent background.
3. `gears.png`: matching gear letters R N 1 2 3 4 5 6 in 24x40 cells, same strip order.
4. `kph.png`, `mph.png`: matching small labels.

Keep text bold: these are tiny on screen. No brand logos.
Write `notes.md` and save everything into `handoff/inbox/0008-speedometer/`.
