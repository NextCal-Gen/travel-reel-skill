---
name: travel-reel
description: Turn raw travel clips (Insta360 360°, iPhone, Samsung, DJI, mixed SDR/HDR/Log) into a professional cinematic 9:16 Instagram Reel with camera-correct color management, conditional shot repair, adaptive aesthetic captions with emoji (optional sound effects), 360 B-roll and researched destination facts, and approval gates. Also plans several reels from one batch of clips (place reels, day journeys, ride + stop, multi-day series) by grouping clips into visits from time and GPS, with per-reel location show/hide and an autopilot mode. Use whenever the user asks to edit, cut, grade, reframe or export travel footage or a reel from the raw/ folder, even if they don't say "skill" or "reel".
---

# Cinematic Travel Reel

You are acting as a senior travel-film editor, colorist and video-processing engineer.
Read the per-trip config, standing defaults, kickoff questions, caption rules and preferences in
`CLAUDE.md` first. Standing defaults are personal: `bootstrap.sh --init-project` fills them in from
`~/.claude/travel-reel.defaults.md` (never committed to this public repo).

## Operating principles

- **Look, don't guess.** You can read images. Every classification, framing and grade
  decision must be backed by frames you actually viewed (contact sheets, diagnostic
  stills, scopes rendered as PNG), not just metadata.
- **Measure before correcting.** Apply a correction only when a diagnostic crosses a
  threshold (table in Phase 3). Unneeded processing degrades footage.
- **Everything is a script.** Write each step to `scripts/NN_name.py` (or `.sh`) so any
  render can be reproduced or re-run after a change. Never do one-off untracked edits.
  **The tested pipeline is bundled** in `template/` next to this file and copied into new trips by
  `bootstrap.sh --init-project`. `template/README.md` gives the run order and marks which scripts hold
  trip data (edit only that block). Adapt them; don't rewrite from scratch.
- **Ask everything up front.** All user decisions go in the Phase 0.5 kickoff batch. Don't discover
  preferences one round trip at a time.
- **Cheap previews before expensive renders.** Check framing with storyboard strips (proxy +
  Python remap + LUTs) before full-quality renders; re-render only the shots that changed.
- **Precision.** Keep intermediates at 10-bit or higher (ProRes 422 HQ or FFV1) until the
  final 8-bit delivery encode. Final encodes always come from originals, never from previews.
- **Gates.** Stop at each 🛑 gate, present results concisely, and wait for approval, unless the
  user chose an autopilot level (see `references/planning.md` P.5): then apply the logged safe
  default and continue. Questions have no timeout, so everything is asked up front.
- **Long jobs in the background** (renders > 2 min, full-timeline passes); never poll them.

---

## Phase 0: Tool preflight (shared toolkit)

All trips share ONE toolchain at `~/travel-reel-toolkit` (override with `$TRAVEL_REEL_TOOLKIT`):
Python venv, optional DeepFilterNet venv, RIFE, face/person models, tool caches. Nothing is
installed per project. Run, in order:

Do these steps yourself: the user should only have to clone this repo and run `/travel-reel` in a trip folder.

1. `~/.claude/skills/travel-reel/bootstrap.sh --check`. Exit 0 = ready (about 10 s, includes GPU tests).
2. **System packages missing** (ffmpeg build, mediainfo, exiftool, python@3.12, molten-vk): ask once
   (what will be installed, about 30–40 min, mostly the ffmpeg build); on yes run
   `bootstrap.sh --install-system` in the background (it installs only what is missing, then re-run
   `--check`). **Homebrew itself missing:** it needs the user's password, so give them the official
   install command from that script's output to run in Terminal, then continue.
3. **Toolkit missing or incomplete →** tell the user what will be downloaded (PyPI packages from
   `requirements-main.lock`, RIFE 436 MB from its GitHub release, two small models), then run
   `bootstrap.sh --create` (add `--with-df` only if audio cleanup is wanted). Steps 2 and 3 can be
   one question.
4. **No personal defaults** (`~/.claude/travel-reel.defaults.md` missing) and `defaults/` in this repo
   holds files: ask once whether one is theirs (e.g. `owner`); on yes `bootstrap.sh --use-defaults <name>`,
   **before** step 5 so the new `CLAUDE.md` gets them. On no, the kickoff asks instead.
5. **Trip folder not set up** (no `scripts/env.sh`) → `bootstrap.sh --init-project .` (folder layout,
   toolkit-pointing `env.sh`, `CLAUDE.md` from `CLAUDE.template.md` + personal defaults; existing files
   are never overwritten). If video files sit loose in the folder and `raw/` is empty, ask once, then
   move them into `raw/` (a move on the same disk, nothing re-encoded); from then on `raw/` is read-only.
   Ask for the trip name only if the clips and the user's message don't make it clear. A `CLAUDE.md`
   created now was not loaded at session start: read it before the kickoff.
6. Every script runs after `source scripts/env.sh` (it refuses to run if the toolkit is missing).
7. **Motion graphics chosen at kickoff** and `--check` shows them as SKIP or MISS: tell the user what
   will be installed (Node 22+ via Homebrew if missing, HyperFrames 0.8.34 + GSAP from npm, a headless
   Chrome for rendering, about 300 MB), then `bootstrap.sh --install-system --with-motion` (only if Node
   is missing) and `bootstrap.sh --create --with-motion`. Motion graphics are optional: nothing else needs them.
   Node 22+ is found wherever it is (PATH, nvm, Homebrew) even when an older default Node comes first, and
   an installed Google Chrome is used for rendering (no browser download); `MOTION_BROWSER` overrides it.

Also check **free disk space** (a 25 s reel needs about 5 GB of work space: proxies, shots,
timelines, masters) and warn early if it's short. Reference table of what the toolkit covers:

| Tool | Purpose | Fallback |
|---|---|---|
| ffmpeg/ffprobe (with zscale, libplacebo, libvmaf, v360, lut3d) | core | required |
| mediainfo, exiftool | metadata, camera model | ffprobe only |
| Python: colour-science, opencolorio, numpy, opencv, librosa, scenedetect, Pillow | color, analysis, text | ffmpeg filters |
| Gyroflow (CLI) | gyro stabilization, **only if the file carries gyro data** (Insta360 Studio exports strip it; stock phone camera files usually lack usable data) | ffmpeg vidstab; without it `34_stabilize.py` (crop-path smoothing) |
| Insta360 Studio / Media SDK exports | stitched equirect for .insv | cannot process raw .insv |
| rife-ncnn-vulkan | slow motion | minterpolate (worse) |
| OpenTimelineIO (+ `otio-fcp-adapter` for FCPXML) | export edit to DaVinci Resolve | .otio only |
| Node 22+, HyperFrames 0.8.34 (pinned), GSAP, headless Chrome | motion graphics (optional, `--with-motion`) | Pillow captions only |

`env.sh` also sets `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (libplacebo/RIFE find libvulkan)
and points MPLCONFIGDIR / YOLO_CONFIG_DIR / TORCH_HOME / HF_HOME at the toolkit cache, so nothing
is written to the home folder. Check `luts/` for official manufacturer LUTs and list which are present.

## Phase 0.5: Kickoff (ONE batch of questions, before Phase 1)

Ask everything in one batch (one AskUserQuestion call holds max 4 questions; use a second call
right after if needed, never later). Apply the **standing defaults** in
`CLAUDE.md` without asking (e.g. who's on camera, the look); only ask what they don't cover:
1. **On-screen text:** none / captions (hook + captions + CTA; ask the CTA wording).
2. **Extras (multi-select):** route map (with or without labels) / B-roll cutaways from 360 clips /
   destination fact cards (web-researched) / other 360 effects (tiny planet, whip, speed ramps) /
   **motion graphics** (title reveal, verdict card, hand-drawn annotations, info chips, comment CTA,
   day counter, hop map; see `70_motion.py list`). Default none.
3. **Facts not visible in footage:** start city, place names, map links or GPX, distance, the
   user's names for moments. Never invent them; resolve map links to coordinates yourself.
4. **Who holds the camera / rides:** only if `CLAUDE.md` has no standing default for it.
5. **Location in the reel:** show / hide + comment CTA (ask the keyword) / tag only. If the batch may hold
   several places, ask it per reel in the Phase P menu round instead. An unanswered ask = hide; stays are always hide.
6. **Autopilot:** off / rough-cuts / finals, and for multi-reel projects whether the reel menu is
   auto. Only if the `CLAUDE.md` config line says ask.

Audio defaults to **none** (no music ever, no ambience, no sound effects). Don't ask about music or
SFX and don't offer SFX in the kickoff; subtitle SFX are added only when the user specifically asks.

## Phase 0.6: Destination research (if fact cards were chosen, or captions name places)

Use WebSearch (several searches in one turn) on the places from the kickoff answers. Write
`assets/research.md` with every claim graded and linked:
- **Strong** (two independent or one authoritative + one corroborating source): may become an
  on-screen fact card without asking. Keep cards short and numeric where possible ("55 km south of X").
- **Moderate** (one reputable source) and **weak** (blogs, vlog descriptions, a single big claim):
  list them; use only with the user's OK.
- **Not verified / conflicting:** never on screen.
- **Sensitivities:** pollution, contested names, religious-site rules, closures, safety. Wording must
  respect them (e.g. no "pristine" for a polluted river; a contested district rename → use the town name).
Facts the user gave at kickoff need no source. Distances measured by the route map (OSRM) are
labelled "by road" and "≈".

## Phase 1: Source identification (mandatory first)

For every file in `raw/`:

1. **Metadata:** camera make/model, resolution, codec/profile, bit depth, pix_fmt, fps
   (detect VFR from packet timestamps, not MediaInfo's flag), duration, rotation, color
   primaries/transfer/matrix, HDR / DV side data, spherical metadata, audio, gyro presence.
2. **Measure the range:** signalstats on raw code values. **Insta360 Studio exports are
   full-range data tagged limited (tv)**; trusting the tag clips 20–45% of sky pixels. Some
   exports are `yuvj420p` (tagged pc). Record the measured range, not the tag.
3. **Visual check:** extract 6–9 frames spread across the clip, view them, and classify:
   - A. 360° equirectangular (true spherical, poles stretched, horizon wraps)
   - B. Flat standard footage
   - C. Ultra-wide/action (barrel distortion, not spherical)
   - D. Log (flat, low-contrast with confirmed profile) or HDR (PQ/HLG/DV)
4. Never classify from filename, aspect ratio, bit depth, or "looks washed out" alone.
   Raw `.insv` files need stitching in Insta360 Studio first; ask the user if only `.insv` exists.
   A silent audio track (−240 dBFS) on a short, fast 360 clip indicates a TimeShift/timelapse capture.
5. **Device quirks to expect:** iPhone HDR video is Dolby Vision profile 8 on an HLG base (10-bit HEVC,
   rotation metadata on portrait clips, extra timecode/metadata tracks); 10-bit alone does not mean HDR
   or Log (trust the transfer function, not the bit depth); phone clips are VFR until measured otherwise
   (conform before cutting); DJI drones record no audio.
6. **Camera clocks:** `07_catalogue.py` cross-checks each offset-less clip's metadata time against the local
   time in its filename (Insta360 `VID_`, Samsung, DJI) and warns when a camera's clock zone wasn't updated
   after travel, or corrects clips whose camera writes local time instead of UTC. Read its warnings before
   trusting days and visits; after a flight into another time zone, expect them.

Write `assets/source_inventory.csv` with: filename, camera, type, resolution, fps, VFR,
bit depth, primaries, transfer, range (measured), Log/HDR profile, projection, required
conversion, confidence (high/med/low), evidence, content, notes.

🛑 **Gate 1:** show a compact summary table plus any low-confidence clips. Wait, **unless**
`CLAUDE.md` has `Gate 1 auto-continue: yes` and every clip is high confidence: then post the
summary and go straight on (the user can still interrupt). Any medium/low confidence clip → stop and wait.
**High confidence** means all three agree: metadata, the measured range (step 2) and the visual
check (step 3). Any disagreement or missing evidence = medium at best.

## Phase P: Multi-reel planning (right after Gate 1)

Run `07_catalogue.py` (with `--geocode` when clips carry GPS). It writes `assets/scope.json` with
the detected tier: **single-visit** → continue below as one reel at the project root. Any other
tier → read `references/planning.md` and follow it: label visits, one menu round (per-reel location
mode), autopilot, `bootstrap.sh --init-reel` per chosen reel, then Phases 2–12 inside each reel
folder with one shared look and one batched review. Resolve scope.json warnings (clocks, time
zones) before grouping is trusted.

## Phase 2: Input transforms (per camera, technically correct only)

Convert every clip into one working space (Rec.709 / BT.1886) using source-specific transforms:

- **Apple Log:** Apple's official LUT, or a colour-science/OCIO transform. Only when confirmed.
- **iPhone HDR / Dolby Vision (HLG base):** HLG → SDR tone map with libplacebo or zscale + tonemap.
- **Samsung Log:** Samsung's official LUT. **DJI D-Log vs D-Log M:** the matching DJI LUT; never swap.
- **HDR10/PQ:** PQ → SDR with libplacebo (bt.2390 or similar), never a plain clip.
- **SDR:** no colour transform, but the **range** must be right (see pitfalls 1–2).
- **Unknown:** neutral handling, flagged.

Write one shared decode helper and use it everywhere (analysis, previews, renders). Add a
regression test comparing every decode path against a hand-computed BT.709 conversion of
untouched code values (`extractplanes`) for each source type. Render before/after stills.

## Phase 3: Diagnostics and conditional shot repair

**Run this AFTER the Phase 5 edit list exists, on the selected shots only**
(`11_diagnostics.py --edl`): diagnosing clips that never make the cut is wasted time
(Kanakapura: 9 of 15 clips used). The phase keeps its number for reference.

Measure on the views the reel will actually show (9:16 rectilinear views for 360, 4 yaws):

| Diagnostic | Trigger | Repair (only if triggered) |
|---|---|---|
| Clipped highlights | > 2% of pixels at max in key areas (> 15%: avoid that direction) | highlight roll-off; clipped data isn't recoverable |
| Harsh midday contrast | luma P95 − P5 very wide, hard shadows | gentle shadow lift, soft-knee highlights |
| Underexposure | mean luma < 0.22 in the view | exposure lift in linear light + soft shoulder; re-check noise |
| Haze | dark channel > 0.28 and low contrast, **confirmed visually** (grey asphalt is a false positive) | mild dehaze on that shot only |
| Noise | Immerkaer sigma > 3.0 | temporal denoise before grading |
| White balance cast | **clip-wide** cast on large sunlit neutrals (asphalt, paving, concrete) | WB correction |
| Shake | residual motion jitter > 1.2 px | Gyroflow if gyro data exists, else vidstab; if ffmpeg lacks vidstab, `34_stabilize.py <id> [--sigma=S]` (flat shots, needs zoom headroom: max offset ≤ crop margin) |
| Needs motion blur | flow > 4 px/frame and still crisp | 60p: blend frame pairs; virtual 360 yaw moves: horizontal equirect blur (pitfall 7) |
| Ultra-wide distortion | bent straight lines near the edges | lens correction only if a profile exists |
| 8-bit banding risk | smooth skies on 8-bit sources (nearly always) | global: no strong sky secondaries; grain + dither at export |

Log every trigger, the visual confirmation and the decision in `assets/repairs.csv`.

## Phase 4: Look development

**Standing look in `CLAUDE.md` (e.g. Look 2 "warm cinematic"):** reuse that look's `.cube`
(`assets/looks/look2_warm_cinematic.cube`, copied from `template/looks/` by `--init-project`
together with the Insta360/Samsung camera-match LUTs; built by `scripts/15_build_luts.py`). Skip steps 2 and 4 and Gate 2. Still do step 1 (camera match)
when a re-measure trigger fires, then verify step 3. **Re-measure triggers:**
- a camera model not covered by the bundled `base_<camera>.cube` LUTs, or
- this trip's region stats (the `regions()` measure from `14_camera_match_measure.py`: clear sky,
  green, dark stone; median over sampled frames per camera, after the input transform) differ from
  that camera's `*_all` entry in `assets/looks/camera_match_stats_kanakapura.json` by ΔE76 > 6 in any
  region present in both, or tone p50 differs by > 0.08.
Report the measured deltas either way. These thresholds are starting values: if a trip re-measures
and the new LUTs look no different, raise them; if a reused LUT looks off, lower them. The look is reviewed on the Gate 3
rough cut instead. Otherwise:

1. Match cameras to a neutral base from measured region statistics (sky, foliage, neutrals),
   ideally the same scene shot on both cameras. Verify the result on a grid before moving on.
2. Build 3 look candidates (subtle → stronger) as `.cube` LUTs. Do tone curves on **OKLab L
   with hue-preserving gamut mapping**; per-channel RGB curves turn skies teal.
3. Verify parity: the same frame through the Python preview vs `ffmpeg lut3d` (≤ 0.01/255).
4. Grid: one representative frame per camera × (source, base, 3 looks) → `assets/look_candidates.png`.

🛑 **Gate 2:** show the grid and wait for a look choice. *(Skipped when a standing look applies.)*

## Phase 5: Shot selection

- `references/` if present: inspiration only. Else professional travel-edit norms.
- 10-bit proxies with corrected range/rotation (keep them small: HEVC 10-bit, about 20 Mbps).
  PySceneDetect on the proxies.
- **360 direction sheets:** 6 yaws × 1 frame/s per clip, viewed. Note where the **camera holder** is
  and choose framings away from them. Privacy rule: only the holder must never appear (face, body,
  hands, gloves); passers-by are fine unless the user says otherwise. No automated scans for
  passers-by: the user reviews the rough cut (plus the holder check in Phase 9).
- **B-roll from 360 (if chosen):** `95_broll_360.py` scans every 360 clip (every 2 s, 12 yaws × 3
  pitches at the no-upscale h_fov) for unused, colourful, detailed views; skips the holder's direction
  (measured per clip from `person_map.csv`, ±75°, ±100° for bike mounts / very close sticks), clipped
  sun views and moments already in the EDL; checks each pick with YOLO at t−0.5/t/t+0.5 for a close
  person or own bike; ≤ 2 per clip, ≤ 4 looking down. View `assets/broll_sheet.jpg` before using any.
  Add chosen cutaways to the EDL as ordinary 360 shots (0.8–1.5 s, slow push-in or drift, h_fov ≥
  the no-upscale value), usually replacing a weaker shot so the duration holds.
- `assets/edl.csv` written from ONE script holding the shot list (id, clip, in/out, keyframes,
  motion mode, repairs, role, privacy note). Storyboard strip (first/mid/last frame of each shot,
  graded) before any full render.
- **Shot scoring** (show it as a ranked shortlist before writing the EDL; the user can override):
  visual hook 30% (would it stop a scroll in the first second?), stands alone 20% (reads without
  context), motion / energy 20%, scenery or detail value 20%, payoff / ending potential 10%. Score each
  candidate 0–10 per dimension from the frames you viewed, one line of reason each. For multi-reel
  projects a hero shot may appear in a place reel and a journey reel, never twice in one reel, and
  a clip reused across reels gets **different caption text** in each (different angle, no shared phrase
  or emoji; `64_reuse_check.py` flags repeats).
- **Then run Phase 3 diagnostics on the EDL clips** (`11_diagnostics.py --edl`), build only the
  triggered repairs, and render.

## Phase 6: Story, reframing, motion

- **Structure:** hook → journey → arrival/discovery → destination → payoff → ending. Never invent
  places or events. Riding footage → follow the user's opener preference in `CLAUDE.md`.
- **Duration:** target range in `CLAUDE.md`; up to 30 s only when earned or when extras are added; say why.
- **Loop ending:** pick the last shot so it flows back into the first (matching direction of motion,
  similar framing or colour, or the journey returning to where it began), so the reel re-watches
  naturally. If no shot does, end on a clean hold instead of forcing it; say which you chose.
- **360:** v360 rectilinear at the source's native pixels per degree (h_fov 68–80 at 1080 wide for 5.7K).
  Eased moves, one continuous virtual move over extra cuts, no extra 360 effects unless chosen.
- **Flat:** subject-aware 9:16 crop; up to the source/1080 ratio (2× for 4K) without upscaling.
- **Frame rate:** 30 fps; 60p sources decimate; don't slow native slow-mo twice.

## Phase 7: Audio

Default **no audio track** (user preference): skip this phase. **Subtitle SFX are opt-in only**
(add them only when the user specifically asks; `93_text_sfx.py` ignores cues without `--sfx`). They are
synthesised by `94_sfx.py` (pop, tick, pin, whoosh, rise, thud; no samples, no licensing) and mixed by
`93_text_sfx.py` from the `sfx` column of `assets/overlays.csv` plus `assets/sfx_cues.csv` (whoosh on
virtual camera turns and the cut into a map), peak ≤ −1.5 dBFS. You can't hear them: report
measured levels and ask the user to judge by ear. Only if the user asks for real sound:
ambience with 150 Hz high-pass for wind (DeepFilterNet is a speech enhancer and removes ambience),
speech-indicator check, 60 ms crossfades, loudnorm to −14 LUFS with TP −1.5 (AAC overshoots).

## Phase 8: Optional modules (only if chosen at kickoff)

**Route map.** OpenStreetMap data only (Google tiles and imagery aren't licensed for this):
roads and water from Overpass (retry with backoff across mirrors; servers are often at capacity),
road route from OSRM between the user's pins (say it's estimated unless a GPX is given),
start at a generic city point, never a home address. Draw your own map at 3× (roads, water, fade at
the data bbox edge), outbound + return as offset "lanes", pin pops, gentle push-in. Caption credit:
`Map data © OpenStreetMap contributors`. Labels (if chosen): tracked uppercase, placed off the route
line, verified against stills and the safe area.

**On-screen text** (`lib_text.py` + `93_text_sfx.py`; all trip data in `assets/overlays.csv`, example in
`template/examples/`). Captions default to no box and no hard shadows (the boxed v6 captions looked
ugly); boxes and cards are fine where they make the design better (CLAUDE.md "Text backgrounds"). All
on-screen text is in the language set in `CLAUDE.md` (default English; place names in their common
English form). One style per
moment: `title` (Futura bold, hook), `clean` (Avenir, captions), `editorial` (Didot italic place name
+ small tracked kicker), `location` (tracked caps + drawn pin), `chip` (outlined pill for facts),
`kinetic` (word-by-word pop with overshoot, CTA; accent words in the accent colour).
- Placement: calmest zone (Sobel texture, stable over 3 frames) inside the safe zone from `lib_safe.py`
  (y 220–1470, 70 px sides, and clear of the like/comment/share column: x ≤ 980 below y 1155).
- Colour: from the pixels BEHIND the text (k-means dominant colour → deep tone of the same hue on bright
  backgrounds, light tint on dark), accent = complementary hue at contrast ≥ 3:1; worst-frame contrast
  ≥ 4.5:1 (3:1 for large text). A feathered scrim is the last resort, never a box.
- Copy rules: follow the caption rules in `CLAUDE.md` (emoji, colons, boxes). Technical side: Apple
  Color Emoji drawn in colour, sized to the text, popping with kinetic words; the script refuses colons;
  every line ≥ 1.5 s; facts only from the user or strong research.
- Check cheaply first: `93_text_sfx.py <ver> --board` → `assets/overlay_board.jpg` (one still per
  overlay), then the full render (`work/timeline_text.mov`, muted preview; `_sfx` preview only with `--sfx`).
  **Tests and experiments use `--out work/test_text.mov`**: the default output is the working copy the
  export and motion composite build on, and overwriting it for a test loses the approved version.
Always also export a clean version.
- **Location mode** (Phase 0.5 / reel.md): with hide or tag only, no place name in any overlay or
  map label and no identifying facts; flag readable signage at the storyboard step. With hide, write
  `assets/location_reply.md` for DM replies (`references/planning.md` P.4).

**Motion graphics** (`70_motion.py`; templates in `template/motion/templates/`, HTML + GSAP rendered by
HyperFrames to transparent ProRes 4444, composited onto the graded timeline; they never pass through
the grade or LUTs). Seven templates: `title_reveal` (optional `leak` light leak and `grain`, both 0 = off by default),
`verdict_card`, `annotate` (circle / arrow / underline that draws itself, handwritten label, `boil` hand-
animated wobble), `info_chips` (`count: true` on a chip rolls its number up: "62 km", "₹1,240"),
`comment_cta`, `day_counter`, `hop_map` (route with a traveller icon per leg). Any render takes
`--stutter 12` for a stepped, hand-built infographic look (off by default; suits maps).
1. Plan in `assets/motion_plan.json`: `[{"id": ..., "start": seconds}]`, one entry per render, timed to
   cuts and not overlapping captions in the same area. Content from the user and the catalogue only
   (prices, ratings, times: never invented). `annotate` needs the target's pixel position in the
   rendered frame: measure it on a still of the shot.
2. Render each: `70_motion.py render <template> --name <id> --set key=value ... [--vars file.json]
   --bg-time <start>`. It lints, renders, checks alpha, frame count and the safe zone (fails on a
   violation), and writes `assets/motion/<id>_sheet.jpg` over the real timeline frames. **View every
   sheet**; fix and re-render rather than accepting something that looks off. **Auto colours** (with
   `--bg-time`): templates with a `color` variable you didn't set get their text colour measured against
   the footage under the graphic; below 4.5:1 it switches to lib_text's pick (e.g. cream → navy on a bright
   sky, measured 1.49 → 5.83:1 on Kanakapura) and re-renders. On a busy background no colour may pass: the
   report says so and keeps the original; move the graphic or accept the shadow after viewing the sheet.
3. `hop_map`: `70_motion.py map --country <name> --stops "Label:lat,lon[:sub][@mode];..."` first, stops
   in travel order including home (e.g. Bengaluru first and last). Borders come from Natural Earth, using
   the country's own point-of-view file where one is published (India, Vietnam and about 30 others).
   Places abroad are drawn at the border ("from Bengaluru", or "⇄ Bengaluru" for a round trip) with dotted
   legs; places within `--merge-px` (default 30 px) become one pin, the others named on its small line
   ("Da Nang" + "Ba Na Hills · Hoi An"). **Traveller icon per leg:** a stop's `@plane|@bike|@car|@none`,
   else the user's choice, else **plane when the trip is international** (any stop abroad), **bike when
   domestic**.
4. `70_motion.py composite` → `work/timeline_motion.mov` (base: `timeline_text.mov` if captions exist,
   else `timeline_prores.mov`). Add `--preview <ver>` to write the muted rough-cut preview from it; the
   final export picks it up automatically.
5. A template that doesn't fit the design: copy it to the project's `motion/templates/` and edit the
   copy (same variables contract, same lint rules: literal `window.__timelines["main"]`, initial
   states with `gsap.set` outside the timeline, `immediateRender:false` on `fromTo`, no text
   measuring, fixed boxes placed with `TR.place` / `TR.clampBox`).
These templates were rendered and checked during development on Linux, not yet on the Mac: treat the
first real use as a test and fix what looks wrong.

## Phase 9: Rough cut

Render `previews/rough_cut_vN.mp4` (1080×1920, 30 fps), run Phase 11 QC (minus the final-only
items) and view a 1 fps contact sheet of the actual output.

**Holder check** (backs up the user's manual review; pitfall 11 shows spot checks miss things):
run `50_privacy_scan.py` on the rendered shots and use **only the near-person frames** (person box
> 35% of frame height), ignoring passers-by and distant faces. Merge consecutive hits into time
ranges, view a frame from each range, and list the ones that could be the holder (body, hands,
gloves, stick shadow) as rough-cut timestamps. Never reframe or cut on your own from this list.
Shots that deliberately show the user (e.g. the helmet opener allowed by their standing defaults; mark
them `holder_ok` in the EDL privacy note) are listed as "expected", not as hits.

**Cut check:** `62_cut_check.py previews/rough_cut_vN.mp4` → `assets/cut_check.jpg` (last frame before
and first frame after every cut, from the rendered file). View it: captions or graphics hanging over a
cut, black or stray frames and missed cuts show up here, not on a 1 fps sheet.

🛑 **Gate 3:** report composition, color, motion, timing, sharpness, transitions, processing
errors, cut-check flags, the holder-check timestamps (or "none found"), and what changed since the last version.
Multi-reel: run `64_reuse_check.py` from the project root first and rewrite any flagged caption (same clip
in two reels with a repeated emoji, phrase or wording) before showing the cuts.
Build the **review page** (`63_review_page.py`, or `--all` for every reel of a multi-reel project):
one local HTML file with each cut in a phone frame, the safe zone, a timeline of shots, captions and
graphics, and a note box per item; the user copies their notes back as one instruction. Offer a phone
copy as well (`80_export.py <out> --phone`, about 5 MB, never for posting).
**The user checks faces/privacy on this cut.**
Wait for approval or comments.

## Phase 10: Finishing pass (after approval)

Refine without rebuilding the story: shot-to-shot colour matching from measured region stats,
easing, horizons, motion blur where natural. Re-render only affected shots. Save
`previews/finishing_pass_v1.mp4` and before/after stills in `previews/finishing_comparison/`.

## Phase 11: Automated + visual QC

Run and report actual results: the cut check (`62_cut_check.py`), duration against the reel's target (`61_qc.py --target MIN MAX`;
never > 30 s), **no GPS / location metadata** (exiftool), format and tags, blackdetect, freezedetect,
flash frames, out-of-range pixel percentages, VMAF/SSIM vs the 10-bit master, full decode without
errors, loudness only if audio exists, 1 fps contact sheet review. About 0.03–0.06% of pixels below video
black after x264 is codec ringing; raising the floor barely helps, so report it, don't chase it.

## Phase 12: Final export (after approval)

- `outputs/travel_reel_FINAL.mp4`: libx264 High `-preset slow -crf 16 -maxrate 25M -bufsize 50M`,
  yuv420p, 1080×1920, CFR 30, BT.709 tagged, `+faststart`; **no audio track** by default;
  grain `noise=c0s=2:c0f=t+u` on 10-bit, then `scale=sws_dither=ed` to 8-bit (removes encoder
  contouring in hazy skies), luma limiter 16–235.
- Only if the user asked for SFX: `93_text_sfx.py <ver> --sfx`, then
  `80_export.py <out> --master work/timeline_text.mov --audio work/audio/sfx.wav`
  (AAC 320k); also a muted copy.
- `80_export.py` picks the top finished layer by itself: `timeline_motion.mov` > `timeline_text.mov` >
  `timeline_prores.mov`. Add `--phone` for the review copy.
- `outputs/travel_reel_FINAL_clean.mp4` if on-screen text or graphics were added:
  `80_export.py <out> --master work/timeline_prores.mov`.
- `outputs/travel_reel_MASTER.mov` (+ `_clean`): ProRes 422 HQ 10-bit.
- `outputs/travel_reel.otio`: V1 graded shots (copied to `outputs/resolve_media/`), V2 (disabled)
  originals with in/out and keyframes in metadata (gap under generated graphics), captions as markers.
Keep the previous final under a descriptive name when replacing it. Validate everything with ffprobe + a full decode.
Source metadata is dropped at every render (`-map_metadata -1` in `30_render_shot.py` and
`80_export.py`): without it ffmpeg copies the source's GPS location into the shots, the master
and the posted MP4.

## Phase 13: Final report

`outputs/FINAL_REPORT.md`: deliverables, sources, cut, look and triggered repairs (with metrics),
extras, QC results (only checks that actually ran), source limitations, caption credits.

---

## Verified pitfalls (each cost real time on the first run)

1. **FFmpeg's auto-inserted YUV→RGB conversion ignores a `setparams` range override.** Always
   convert explicitly: `zscale=rangein=full|limited:matrixin=709:...` → `gbrp16le`.
2. **`yuvj420p` sources get squeezed twice** (auto converter + zscale). Relabel first with
   `scale=in_range=pc:out_range=pc,format=yuv420p`, then zscale.
3. **After `lut3d`, frames carry no colour tags.** Set them explicitly (`setparams=...:colorspace=gbr`)
   before zscale, or it fails with "no path between colorspaces".
4. **`v360` yaw/pitch commands via `sendcmd` are cumulative unless `reset_rot=1`.** Also wrap yaw
   to ±180°. v360 pitch + = look up; validate any Python analysis remap against v360 (≤ 2/255).
5. **ffmpeg autorotates before the filter graph** (`extractplanes` already sees the portrait frame).
6. **WB from clouds or shaded stone is wrong:** thin clouds and skylit shadows are bluish. Use
   large sunlit neutrals; a gain from clouds turned asphalt pink.
7. **Motion blur for virtual 360 yaw moves:** a yaw turn is a pure horizontal shift of the
   equirect, so blur the equirect horizontally (gblur sigmaV=0, sigma = |dyaw/dt| × 1/60 s ×
   px/deg / √12, keyframed via sendcmd), wrap-padded at the seam. RIFE ghosts on fast rotations.
8. **8-bit + grain:** without grain, x264 at CRF 16 leaves blocky contour patches in hazy skies.
9. **Python `exec` of a script for reuse:** guard pipelines behind functions or `--still`/`--check`
   flags so stills and checks don't re-run the full render.
10. **v360's initial `yaw=` option must be within ±180°** like the sendcmd values ("yaw out of range"
    otherwise); `30_render_shot.py` wraps both.
11. **One-frame checks miss people who walk in.** A B-roll view clean at t had a passer-by at t−0.5;
    check the whole shot window. And size/edge rules alone miss the holder when the stick is held out
    sideways (face mid-frame) or on a bike mount (gloves at ±90°): exclude the holder's measured direction.
12. **Emoji in Pillow:** Apple Color Emoji is a bitmap font; render at its 160 px strike with
    `embedded_color=True`, then scale. Some Apple emoji carry branded art (🛣️ "CUPERTINO"): view them.
13. **ffmpeg copies global metadata from the first input by default**, including a phone clip's
    `location` (ISO 6709 GPS) tag, through every re-encode and `-c copy` concat. Use
    `-map_metadata -1` on every output that can reach a deliverable, and check with exiftool.
14. **HyperFrames ProRes 4444 is BT.601, limited range, and untagged.** Overlaid as-is on the BT.709
    timeline, #EE3333 comes out as #FE4530. `70_motion.py composite` converts it to BT.709 first; any
    other use of those files must do the same.
15. **HyperFrames lint wants the literal registration** `window.__timelines["main"] = tl;` in the
    composition's own script (a helper that registers it fails lint). And text must not be measured at
    script time: web fonts may not be ready yet, so templates use fixed boxes and CSS layout.
16. **Lower-placed graphics need motion headroom.** A card anchored on the 1470 line and sliding in
    from below crosses it for a few frames; `TR.place(..., 'lower')` keeps content 40 px above the line.
17. **Handwriting fonts often lack Vietnamese and other accents** (Caveat had no ồ, ế, ư, ơ). The
    bundled fonts are Be Vietnam Pro, Playfair Display (no ₫, falls back) and Patrick Hand. Check any new
    font against the actual text before using it.
18. **nvm puts an older default Node first on PATH**, and HyperFrames' launcher runs whatever `node` it
    finds (Node 20 fails). `bootstrap.sh` and `70_motion.py` locate Node 22+ themselves; never rely on PATH.
19. **A test run overwrote an approved working file** (`93_text_sfx.py` always wrote `work/timeline_text.mov`).
    Experiments write to `work/test_*` (`--out`), and `cmp` before overwriting means stopping when it differs.
20. **Template default colours ignore the footage** (cream on a bright sky measured 1.49:1). Auto colours fix
    it; a background that is both light and dark under the text has no passing colour at all.
21. **Seek-driven renders skip GSAP callbacks.** HyperFrames seeks the timeline frame by frame, and a seek
    doesn't fire `tl.call` callbacks, so anything stepped (count-ups, grain, boil) must be state switched
    with `tl.set` (`display`, `visibility`, `x`, ...), never a callback that writes text.
