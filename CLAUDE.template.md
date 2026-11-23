# Travel Reel Project

Raw travel clips in, cinematic Instagram Reel out. The full workflow lives in the
`travel-reel` skill (`~/.claude/skills/travel-reel/SKILL.md`). Run it with `/travel-reel`.

## Per-trip config (edit these lines only)
- Trip name: <e.g. Coorg ride, Nov 2026>
- Target duration: 18–25 s (hard max 30 s; up to 30 s is fine when extras such as a map are added)
- Timeline fps: 30 (change only if justified)
- Look: natural cinematic: warm sun, rich greens, clean skies, soft highlight roll-off
- Look reference (optional): references/look/
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

## Ask me once at kickoff (one batch, before Phase 1), then don't ask again
1. **On-screen text?** None / captions (hook + captions + CTA; what the CTA says).
2. **Extras?** Any of: route map (with or without labels), B-roll cutaways from 360 clips, destination fact
   cards (web-researched, sourced), other 360 effects (tiny planet, whip transitions, speed ramps). Default none.
3. **Facts you can't see in the footage:** start city, place names, map links or GPX, distance, what I call
   moments (e.g. "river crossing"). Don't invent any of these.
4. **Who holds the camera / rides?** (skip if a standing default covers it)

## Caption copy rules
- Emoji where they add meaning (🏍️ ride, 🛕 temple, 🪷 lily pond, 📍 distance, 📩 DM CTA); none on serif
  "editorial" place names. Avoid emoji with branded artwork (Apple's 🛣️ shows a "CUPERTINO" sign).
- No colons in on-screen text; use " - " only if a break is needed.
- No boxes behind text: colours and placement are chosen from the frame (lib_text).

## Preferences
- Keep 360 clips natural: no extra 360 effects unless chosen at kickoff.
- If I pick on-screen text: also export a **clean version** without it.
- **No automated face/privacy scans of the reel.** Pick framings away from the camera holder; I review
  the rough cut myself and flag anything before final approval.

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
- Stop at every approval gate and wait for my reply (except where standing defaults allow
  auto-continue). Never export finals without an approved rough cut.
- Never claim a check was done unless it actually ran. Report source limitations honestly.
- No voiceover, no music, no logos, no copyrighted reference footage.
- No burned-in text unless I opted in at kickoff (captions, map labels); then also export a clean version.
- On-screen facts only from me or from strong sources in `assets/research.md`.
