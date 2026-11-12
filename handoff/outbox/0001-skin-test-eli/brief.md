# Task 0001: skin test on the Lotus Elise (car id `eli`)

Goal: test whether an AI-painted skin lines up with the car and how the game tints it.
This is a small test, not a final skin.

## Files you received
- `texture.png`  the original 256x256 texture (the game's yellow body "mask").
- `uv_guide.png` the same texture at 1024x1024 with cyan lines showing where each 3D panel
  sits. Use it only to understand the layout. Do NOT put the cyan lines in your output.
- `uv_plain.png` the same lines on black, if easier to read.

## What the texture is
- One flat sheet with all panels of the car (sides, hood, roof, rear, lights, wheel arches).
- Yellow areas are body paint. The darker and lighter yellow shading is baked-in lighting
  (reflections, creases). Keep that shading, it is what makes the car look 3D.
- Grey, black and blue areas are glass, lights, tyres, underbody and vents. Do not repaint
  these. The black area at the bottom of the sheet is unused: leave it black.
- The game tints the yellow, so the final colour in game may differ from what you paint.
  That is part of what we are testing.

## Make two variants
Both must be 1024x1024 PNG, same layout as `uv_guide.png` (every panel in exactly the same
place, same orientation, nothing cropped, rotated or shifted):

1. `skin_a_red_white.png`: body paint repainted red, with two white racing stripes running
   along the full length of the car (hood, roof, rear deck). Keep the baked shading.
2. `skin_b_stripes_only.png`: leave the yellow exactly as is and only add the two white
   stripes in the same places.

Stripes must continue across panels at the seams (hood to roof to rear). Use the cyan lines
in `uv_guide.png` to see which panels connect.

## Return
- The two PNG files above, named exactly like that.
- `notes.md`: which panels you could not identify, what you were unsure about, and anything
  that did not line up.
