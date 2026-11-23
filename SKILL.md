---
name: travel-reel
description: Turn raw travel clips (Insta360 360°, iPhone, Samsung, DJI, mixed SDR/HDR/Log) into a professional cinematic 9:16 Instagram Reel with camera-correct color management, conditional shot repair, adaptive aesthetic captions with emoji and sound effects, 360 B-roll and researched destination facts, and approval gates. Use whenever the user asks to edit, cut, grade, reframe or export travel footage or a reel from the raw/ folder, even if they don't say "skill" or "reel".
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
- **Gates.** Stop at each 🛑 gate, present results concisely, and wait for approval.
- **Long jobs in the background** (renders > 2 min, full-timeline passes); never poll them.

---

## Phase 0: Tool preflight (shared toolkit)

All trips share ONE toolchain at `~/travel-reel-toolkit` (override with `$TRAVEL_REEL_TOOLKIT`):
Python venv, optional DeepFilterNet venv, RIFE, face/person models, tool caches. Nothing is
installed per project. Run, in order:

1. `~/.claude/skills/travel-reel/bootstrap.sh --check`. Exit 0 = ready (about 10 s, includes GPU tests).
2. **Toolkit missing or incomplete →** tell the user what will be downloaded (PyPI packages from
   `requirements-main.lock`, RIFE 436 MB from its GitHub release, two small models), then run
   `bootstrap.sh --create` (add `--with-df` only if audio cleanup is wanted). **System packages
   (Homebrew ffmpeg tap build, molten-vk, mediainfo, exiftool, python@3.12) are never auto-installed:**
   the check prints the exact command; ask the user before running it.
3. New trip folder without `scripts/env.sh` → `bootstrap.sh --init-project <dir>` (folder layout,
   toolkit-pointing `env.sh`, `CLAUDE.md` from `CLAUDE.template.md`; existing files are never overwritten).
4. Every script runs after `source scripts/env.sh` (it refuses to run if the toolkit is missing).

Also check **free disk space** (a 25 s reel needs about 5 GB of work space: proxies, shots,
timelines, masters) and warn early if it's short. Reference table of what the toolkit covers:

| Tool | Purpose | Fallback |
|---|---|---|
| ffmpeg/ffprobe (with zscale, libplacebo, libvmaf, v360, lut3d) | core | required |
| mediainfo, exiftool | metadata, camera model | ffprobe only |
| Python: colour-science, opencolorio, numpy, opencv, librosa, scenedetect, Pillow | color, analysis, text | ffmpeg filters |
| Gyroflow (CLI) | gyro stabilization | ffmpeg vidstab |
| Insta360 Studio / Media SDK exports | stitched equirect for .insv | cannot process raw .insv |
| rife-ncnn-vulkan | slow motion | minterpolate (worse) |
| OpenTimelineIO (+ `otio-fcp-adapter` for FCPXML) | export edit to DaVinci Resolve | .otio only |

`env.sh` also sets `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (libplacebo/RIFE find libvulkan)
and points MPLCONFIGDIR / YOLO_CONFIG_DIR / TORCH_HOME / HF_HOME at the toolkit cache, so nothing
is written to the home folder. Check `luts/` for official manufacturer LUTs and list which are present.

## Phase 0.5: Kickoff (ONE batch of questions, before Phase 1)

Ask everything in one AskUserQuestion call (max 4 questions). Apply the **standing defaults** in
`CLAUDE.md` without asking (e.g. who's on camera, the look); only ask what they don't cover:
1. **On-screen text:** none / captions (hook + captions + CTA; ask the CTA wording) / captions + subtitle SFX.
2. **Extras (multi-select):** route map (with or without labels) / B-roll cutaways from 360 clips /
   destination fact cards (web-researched) / other 360 effects (tiny planet, whip, speed ramps). Default none.
3. **Facts not visible in footage:** start city, place names, map links or GPX, distance, the
   user's names for moments. Never invent them; resolve map links to coordinates yourself.
4. **Who holds the camera / rides:** only if `CLAUDE.md` has no standing default for it.

Audio defaults to **none** (no music ever, no ambience); the only sound is the subtitle SFX track,
and only if chosen in question 1. Don't ask about music.

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

Write `assets/source_inventory.csv` with: filename, camera, type, resolution, fps, VFR,
bit depth, primaries, transfer, range (measured), Log/HDR profile, projection, required
conversion, confidence (high/med/low), evidence, content, notes.

🛑 **Gate 1:** show a compact summary table plus any low-confidence clips. Wait, **unless**
`CLAUDE.md` allows auto-continue and every clip is high confidence: then post the summary and
go straight on (the user can still interrupt). Any medium/low confidence clip → stop and wait.

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
| Shake | residual motion jitter > 1.2 px | Gyroflow if gyro data exists, else vidstab |
| Needs motion blur | flow > 4 px/frame and still crisp | 60p: blend frame pairs; virtual 360 yaw moves: horizontal equirect blur (pitfall 7) |
| Ultra-wide distortion | bent straight lines near the edges | lens correction only if a profile exists |
| 8-bit banding risk | smooth skies on 8-bit sources (nearly always) | global: no strong sky secondaries; grain + dither at export |

Log every trigger, the visual confirmation and the decision in `assets/repairs.csv`.

## Phase 4: Look development

**Standing look in `CLAUDE.md` (e.g. Look 2 "warm cinematic"):** reuse that look's `.cube`
(`assets/looks/look2_warm_cinematic.cube`, copied from `template/looks/` by `--init-project`
together with the Insta360/Samsung camera-match LUTs; built by `scripts/15_build_luts.py`). Skip steps 2 and 4 and Gate 2. Still do step 1 (camera match)
for new cameras or clearly different light, then verify step 3. The look is reviewed on the Gate 3
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
  hands, gloves); passers-by are fine unless the user says otherwise. No automated per-frame face
  scans of the reel: the user reviews the rough cut.
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
- **Then run Phase 3 diagnostics on the EDL clips** (`11_diagnostics.py --edl`), build only the
  triggered repairs, and render.

## Phase 6: Story, reframing, motion

- **Structure:** hook → journey → arrival/discovery → destination → payoff → ending. Never invent
  places or events. Riding footage → follow the user's opener preference in `CLAUDE.md`.
- **Duration:** target range in `CLAUDE.md`; up to 30 s only when earned or when extras are added; say why.
- **360:** v360 rectilinear at the source's native pixels per degree (h_fov 68–80 at 1080 wide for 5.7K).
  Eased moves, one continuous virtual move over extra cuts, no extra 360 effects unless chosen.
- **Flat:** subject-aware 9:16 crop; up to the source/1080 ratio (2× for 4K) without upscaling.
- **Frame rate:** 30 fps; 60p sources decimate; don't slow native slow-mo twice.

## Phase 7: Audio

Default **no audio track** (user preference): skip this phase. **Subtitle SFX** (if chosen) are
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
`template/examples/`). No boxes or hard shadows (users found the boxed v6 captions ugly). One style per
moment: `title` (Futura bold, hook), `clean` (Avenir, captions), `editorial` (Didot italic place name
+ small tracked kicker), `location` (tracked caps + drawn pin), `chip` (outlined pill for facts),
`kinetic` (word-by-word pop with overshoot, CTA; accent words in the accent colour).
- Placement: calmest zone (Sobel texture, stable over 3 frames) inside the safe area (14–80% height).
- Colour: from the pixels BEHIND the text (k-means dominant colour → deep tone of the same hue on bright
  backgrounds, light tint on dark), accent = complementary hue at contrast ≥ 3:1; worst-frame contrast
  ≥ 4.5:1 (3:1 for large text). A feathered scrim is the last resort, never a box.
- Copy rules (CLAUDE.md): emoji where meaningful (Apple Color Emoji, drawn in colour, sized to the text,
  popping with kinetic words), never on editorial names; **no colons** (the script refuses them); every
  line ≥ 1.5 s; facts only from the user or strong research.
- Check cheaply first: `93_text_sfx.py <ver> --board` → `assets/overlay_board.jpg` (one still per
  overlay), then the full render (`work/timeline_text.mov`, muted preview + `_sfx` preview).
Always also export a clean version.

## Phase 9: Rough cut

Render `previews/rough_cut_vN.mp4` (1080×1920, 30 fps), run Phase 11 QC (minus the final-only
items) and view a 1 fps contact sheet of the actual output.

🛑 **Gate 3:** report composition, color, motion, timing, sharpness, transitions, processing
errors, and what changed since the last version. **The user checks faces/privacy on this cut.**
Wait for approval or comments.

## Phase 10: Finishing pass (after approval)

Refine without rebuilding the story: shot-to-shot colour matching from measured region stats,
easing, horizons, motion blur where natural. Re-render only affected shots. Save
`previews/finishing_pass_v1.mp4` and before/after stills in `previews/finishing_comparison/`.

## Phase 11: Automated + visual QC

Run and report actual results: duration (≤ 30 s), format and tags, blackdetect, freezedetect,
flash frames, out-of-range pixel percentages, VMAF/SSIM vs the 10-bit master, full decode without
errors, loudness only if audio exists, 1 fps contact sheet review. About 0.03–0.06% of pixels below video
black after x264 is codec ringing; raising the floor barely helps, so report it, don't chase it.

## Phase 12: Final export (after approval)

- `outputs/travel_reel_FINAL.mp4`: libx264 High `-preset slow -crf 16 -maxrate 25M -bufsize 50M`,
  yuv420p, 1080×1920, CFR 30, BT.709 tagged, `+faststart`; **no audio track** by default;
  grain `noise=c0s=2:c0f=t+u` on 10-bit, then `scale=sws_dither=ed` to 8-bit (removes encoder
  contouring in hazy skies), luma limiter 16–235.
- With SFX chosen: `80_export.py <out> --master work/timeline_text.mov --audio work/audio/sfx.wav`
  (AAC 320k); also a muted copy.
- `outputs/travel_reel_FINAL_clean.mp4` if on-screen text was added.
- `outputs/travel_reel_MASTER.mov` (+ `_clean`): ProRes 422 HQ 10-bit.
- `outputs/travel_reel.otio`: V1 graded shots (copied to `outputs/resolve_media/`), V2 (disabled)
  originals with in/out and keyframes in metadata (gap under generated graphics), captions as markers.
Keep the previous final under a descriptive name when replacing it. Validate everything with ffprobe + a full decode.

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
