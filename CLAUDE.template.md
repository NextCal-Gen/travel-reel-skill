# Travel Reel Project

Raw travel clips in, cinematic Instagram Reel out. The full workflow lives in the
`travel-reel` skill (`~/.claude/skills/travel-reel/SKILL.md`). Run it with `/travel-reel`.

## Per-trip config (edit these lines only)
- Trip name: <e.g. Coorg ride, Nov 2026>
- Target duration: 18–25 s (hard max 30 s; up to 30 s is fine when extras such as a map are added)
- Timeline fps: 30 (change only if justified)
- Look: natural cinematic: warm sun, rich greens, clean skies, soft highlight roll-off
- Look reference (optional): references/look/
- Opener: <e.g. "riding POV hook" / "destination reveal first"; leave blank to let the footage decide>
- Gate 1 auto-continue: no  (yes = skip the inventory stop when every clip is high confidence)
- Autopilot: ask  (off / rough-cuts / finals / ask; ask = one kickoff question. No answer timeout exists:
  autopilot works by asking everything up front)
- Reel menu: ask  (ask = I pick reels from the proposed menu; auto = tier defaults + standing menu defaults)
- Location in reel: ask  (show / hide / tag-only / ask, per reel; an unanswered ask = hide; stay reels
  are always hide unless I say show)
- Comment keyword: <e.g. LOCATION; used by the hide + comment CTA>
- Audio: **none** (no music, no ambience, no sound effects). Subtitle sound effects (pop, pin, whoosh...)
  only if I specifically ask for them; never offer or add them by default.
- Faces: the camera holder must never appear (answer "who holds the camera" at kickoff);
  other people in frame are fine unless I say otherwise.

<!-- standing-defaults:start -->
## Standing defaults (don't ask; apply unless I say otherwise for a trip)
None yet. Ask the kickoff questions; when an answer repeats across trips, save it in
`~/.claude/travel-reel.defaults.md` (copied into this block by `bootstrap.sh --init-project`).
- **Look:** Look 2 "warm cinematic" from `assets/looks/` is offered first; build look candidates only
  if I don't want it.
<!-- standing-defaults:end -->

## Kickoff
Ask the Phase 0.5 kickoff questions from the skill once, in one batch, before Phase 1. Skip anything the
config or standing defaults above already answer. Don't ask again later in the trip. Multi-reel projects
add one menu round after the catalogue (skipped when `Reel menu: auto`).

## Caption copy rules
- Emoji where they add meaning (🏍️ ride, 🛕 temple, 🪷 lily pond, 📍 distance, 📩 DM CTA); none on serif
  "editorial" place names. Avoid emoji with branded artwork (Apple's 🛣️ shows a "CUPERTINO" sign).
- No colons in on-screen text; use " - " only if a break is needed.
- No boxes behind text: colours and placement are chosen from the frame (lib_text).

## Preferences
- Keep 360 clips natural: no extra 360 effects unless chosen at kickoff.
- If I pick on-screen text: also export a **clean version** without it.
- **No automated scans for passers-by.** Pick framings away from the camera holder; I review the rough
  cut myself before final approval. One exception: a **holder check** on the rough cut (near-person
  detections only, listed as timestamps for me to look at; never auto-edited).

## Folder layout
- Tools: shared toolkit at `~/travel-reel-toolkit` (venv, RIFE, models, caches); one copy for all trips.
  Checked or created by `~/.claude/skills/travel-reel/bootstrap.sh`; never installed per project.
- `raw/`: original clips. READ-ONLY. Never modify, move or re-encode in place.
- `references/`: reference reels (inspiration only) and `references/look/` stills or LUTs
- `luts/`: official manufacturer LUTs only
- `assets/`: inventory, analysis, EDL, map data, research, overlays
- `scripts/`: every processing step as a re-runnable script
- `work/`: proxies, intermediates (safe to delete)
- `previews/`, `outputs/`: renders

## Hard rules
- Identify camera, projection and color profile of every clip before any processing.
- Never dewarp flat footage. Never apply a Log LUT unless the Log profile is confirmed.
- Corrections are applied only when a measured diagnostic crosses its threshold. Log why.
- Stop at every approval gate and wait for my reply. Exceptions: Gate 1 when `Gate 1 auto-continue: yes`
  and every clip is high confidence; and the autopilot level I chose (rough-cuts or finals), which applies
  logged safe defaults instead of asking. Never export finals without an approved rough cut, unless I chose
  `Autopilot: finals` for this project.
- Never claim a check was done unless it actually ran. Report source limitations honestly.
- No voiceover, no music, no logos, no copyrighted reference footage.
- No burned-in text unless I opted in at kickoff (captions, map labels); then also export a clean version.
- On-screen facts only from me or from strong sources in `assets/research.md`.
- No GPS or device metadata in any deliverable; a hidden location must not leak through captions, map
  labels, fact cards or readable signs.
