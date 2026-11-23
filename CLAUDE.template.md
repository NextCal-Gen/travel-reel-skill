# Travel Reel Project

Raw travel clips in, cinematic Instagram Reel out. The full workflow lives in the
`travel-reel` skill (`~/.claude/skills/travel-reel/SKILL.md`). Run it with `/travel-reel`.

## Per-trip config (edit these lines only)
- Trip name: <e.g. Coorg ride, Nov 2026>
- Target duration: 18–25 s (hard max 30 s; up to 30 s is fine when extras such as a map are added)
- Timeline fps: 30 (change only if justified)
- Look: natural cinematic: warm sun, rich greens, clean skies, soft highlight roll-off
- Look reference (optional): references/look/
- Audio: **none**. Never add music. Deliver with no audio track (no music, no ambience) unless I ask.
- Faces: my face must never appear; avoid identifiable faces of others

## Standing defaults (don't ask; apply unless I say otherwise for a trip)
- **The person holding the 360 stick / riding the bike is me.** My face must never be visible;
  me in a full-face helmet with the visor down is fine on camera.
- **Look: Look 2 "warm cinematic"** (approved on the Kanakapura reel). Reuse it; don't build look
  candidates or stop at the look gate. Re-measure the camera match only for new cameras or very
  different light. A new look only if I ask.
- **Gate 1 auto-continue:** if every clip is identified with high confidence, show the inventory
  summary and carry on without waiting. Stop at Gate 1 only when something is medium/low confidence.

## Ask me once at kickoff (one batch, before Phase 1), then don't ask again
1. **On-screen text?** None, or burned-in hook + captions + CTA (and what the CTA says, e.g. DM "RIDE").
2. **Extras / gimmicks?** None, or route map (with or without place labels), or other 360 effects
   (tiny planet, whip transitions, speed ramps). Default: none.
3. **Facts you can't see in the footage:** start city, place names, map links or GPX, distance, what I call
   moments (e.g. "river crossing"). Don't invent any of these.

## My preferences (learned on the Kanakapura reel)
- Riding footage available → **open on the ride**: me in helmet → one eased 180° turn to the road ahead
  → stop and hold. No multi-turn spins.
- Keep 360 clips natural: no extra 360 effects unless I chose them at kickoff.
- If I pick on-screen text: also export a **clean version** without it.
- **No automated face/privacy scans.** Pick framings away from me and from close faces of others;
  I'll review the rough cut myself and flag anything before final approval.

## Folder layout
- Tools: shared toolkit at `~/travel-reel-toolkit` (venv, RIFE, models, caches); one copy for all trips.
  Checked or created by `~/.claude/skills/travel-reel/bootstrap.sh`; never installed per project.
- `raw/`: original clips. READ-ONLY. Never modify, move or re-encode in place.
- `references/`: reference reels (inspiration only) and `references/look/` stills or LUTs
- `luts/`: official manufacturer LUTs only
- `assets/`: inventory, analysis, EDL, map data
- `scripts/`: every processing step as a re-runnable script
- `work/`: proxies, intermediates (safe to delete)
- `previews/`, `outputs/`: renders

## Hard rules
- Identify camera, projection and color profile of every clip before any processing.
- Never dewarp flat footage. Never apply a Log LUT unless the Log profile is confirmed.
- Corrections are applied only when a measured diagnostic crosses its threshold. Log why.
- Stop at every approval gate and wait for my reply (except Gate 1 auto-continue and the look gate,
  per standing defaults). Never export finals without an approved rough cut.
- Never claim a check was done unless it actually ran. Report source limitations honestly.
- No voiceover, no music, no logos, no copyrighted reference footage.
- No burned-in text unless I opted in at kickoff (captions, map labels); then also export a clean version.
