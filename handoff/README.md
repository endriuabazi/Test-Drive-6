# Handoff folder: Claude Code <-> ChatGPT

Two AIs, one person in the middle. Neither AI can read this folder from the other side, so
the user moves files by hand (drag and drop, or paste text).

## Folders
- `outbox/<task-id>/`  Claude Code writes here. One folder per task: `brief.md` plus the
  files ChatGPT needs (texture PNG, UV guide, OBJ preview, references).
- `inbox/<task-id>/`   The user saves ChatGPT's results here. Same task id.
- `done/<task-id>/`    Finished tasks are moved here after Claude Code imports them.

## Flow
1. Claude Code creates `outbox/<task-id>/` with `brief.md` and files.
2. User uploads those files to ChatGPT and pastes the brief (or just the text of `brief.md`).
3. ChatGPT produces the result and a short `notes.md` (what it did, what it is unsure about).
4. User saves the result files into `inbox/<task-id>/` and tells Claude Code (or Claude Code
   notices the new files).
5. Claude Code checks, converts, imports into a COPY of the game files, and reports back.

Task ids look like `0001-mercedes-skin`.

## Rules for ChatGPT (paste this once at the start of the ChatGPT chat or project)
You work on a hobby mod for the old PC game Test Drive 6. A person relays files between you
and another AI (Claude Code) that does the game-file conversion. You only produce art or
concept files, never game files.

When you get a `brief.md` and files:
- Follow the brief. If it conflicts with these rules, the brief wins, but say so in notes.
- Car textures are 256x256 pixels. Work at a larger size if you like, but keep the exact same
  layout as the supplied texture and UV guide: every panel must stay where it is. Do not
  rotate, move, crop or add margins. The final image must have the same aspect ratio (1:1).
- Return PNG files. Name them exactly as the brief says. Add `notes.md` with what you changed
  and anything you are unsure about (for example panels you could not identify).
- Do not draw real brand logos or trademarks unless the brief explicitly asks for them. This
  is a private fan mod, but keep text and logos simple, they shrink to 256x256.
- If something in the brief is unclear, ask the person one short question instead of guessing.

## What Claude Code does with the results
- Resizes to 256x256, converts to the game's BGRA TGA, imports into `cars/<id>.zip` of a copy.
- Works on this modded install (clean backup: `C:\MagiPacks\Test Drive 6`). `TD6.exe` is never
  edited, only copies of it.
