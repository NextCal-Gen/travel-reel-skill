# travel-reel pipeline template

Tested end-to-end on the Kanakapura reel (Nov 2026, Insta360 X4/X5 exports + Samsung S24 Ultra).
`bootstrap.sh --init-project <dir>` copies `scripts/` and the standing look into a new trip folder.
Always `source scripts/env.sh` first (shared toolkit).

**Generic** scripts run as-is. **Trip** scripts hold the last trip's data in one clearly named
block (clip names, shot list, captions, coordinates...). Rewrite that block from what you see in
this trip's footage; keep the code around it.

## Run order

| Step | Script | Kind | What to edit for a new trip |
|---|---|---|---|
| Metadata | `01_extract_metadata.sh` → `02_summarize_metadata.py` | generic | – |
| Range + VFR (measured, not tags) | `04_verify_range_vfr.py`, `05_range_compare.sh <clip> <t>` | generic | – |
| Contact sheets (view them) | `03_contact_sheets.py` | generic | – |
| Inventory | `06_write_inventory.py` | **trip** | `V = {...}` per clip: camera, type, content, privacy, notes (from viewing) |
| 🛑 Gate 1 (auto-continue if all high confidence) | | | |
| Catalogue + visits (multi-reel) | `07_catalogue.py [--geocode]` → `assets/visits.csv`, `scope.json` | generic | – (thresholds via flags) |
| Per-reel project (multi-reel) | `bootstrap.sh --init-reel <project> <id>` | – | `reel.md` in the reel folder |
| Decode regression test | `17_verify_decode.py` | **trip** | `CASES`: one clip per source type (yuvj / mis-tagged / rotated) |
| Input transforms | `10_input_transforms.py` | generic | – |
| Look (only if NOT using the standing look) | `14_camera_match_measure.py` → `15_build_luts.py` → `16_look_grid.py` | **trip** (14, 16) | matched-scene clips/times; grid shots |
| Proxies, scenes | `20_proxies.sh`, `22_scenedetect.py` | generic | – |
| 360 direction sheets | `21_direction_sheets.py [clip ...]` | generic | – (face detection optional) |
| Edit list | `23_edl.py` | **trip** | `SHOTS = [...]`: clip, in/out, keyframes, nd, repairs, role |
| Storyboard (cheap check) | `24_storyboard.py` | generic | – |
| Diagnostics on selected shots | `11_diagnostics.py --edl` → `12_evaluate_triggers.py` | **trip** (12) | `VISUAL_REVIEW` confirmations |
| Diagnostic views | `13_diag_views.py <clip> <t> <yaw\|flat> [pitch fov]` | generic | – |
| Repair LUTs (triggered only) | `31_repair_luts.py` | **trip** | which shots/repairs and their parameters |
| Render shots from originals | `30_render_shot.py [S01 ...]` | **trip** | `REPAIR_LUT`, `FINISH_LUT` shot→LUT maps |
| Motion check / shot sheet | `33_motion_check.py <id>`, `32_shot_sheet.py` | generic | – |
| Stabilise flat shot (no gyro, no vidstab) | `34_stabilize.py <id> [--sigma=0.18]` → `assets/stab/<id>.json`, used by `30_render_shot.py` | generic | zoom headroom on the shot in `23_edl.py` |
| Route map (optional) | `90_fetch_osm.sh`, `91_route_map.py` | **trip** (91; bbox in 90) | `PTS` pins, routes, labels, bbox |
| Destination research (optional) | WebSearch → `assets/research.md` | – | graded facts (SKILL.md Phase 0.6) |
| B-roll from 360 (optional) | `95_broll_360.py` → view `assets/broll_sheet.jpg` | generic | add picks to `23_edl.py` as 360 shots |
| SFX library (only if the user asks for SFX) | `94_sfx.py` | generic | – (writes `assets/sfx/*.wav`) |
| On-screen text (optional; SFX opt-in with `--sfx`) | `93_text_sfx.py <ver> --board`, then `93_text_sfx.py <ver> [--sfx] [--out FILE]` (tests: `--out work/test_text.mov`) | generic | `assets/overlays.csv` (optional `zone` column, e.g. `0.62\|0.70`, when the default zones land on busy areas), `assets/sfx_cues.csv` (see `examples/`) |
| Motion graphics (optional) | `70_motion.py list` / `map` / `render <template> --name ID --set k=v` → `composite --preview <ver>` | generic | `assets/motion_plan.json` |
| Rough cut | `60_assemble.py <ver> --mute` → `61_qc.py <file> [master] [--target MIN MAX]` → `62_cut_check.py <file>` | generic | – |
| Caption reuse across reels (multi-reel, project root) | `64_reuse_check.py [--strict]` → `assets/reuse_check.json` (same clip in two reels/shots + repeated emoji, phrase or wording) | generic | – |
| Review page | `63_review_page.py [--all]` → `previews/review.html` (phone frame, safe zone, timeline, notes → instructions) | generic | – |
| 🛑 Gate 3 (user checks faces on the rough cut) | | | |
| Finishing | `70_shot_match.py` → `71_finishing_trims.py` | **trip** | ground regions; trims for measured outliers |
| Export | `80_export.py <out> [--master FILE] [--audio work/audio/sfx.wav] [--phone]` (default master: motion > text > clean timeline) | generic | – |
| Master + Resolve | `81_export_master_otio.py` | **trip** | timeline name |
| Audio (only if asked) | `40_audio_analysis.py`, `41_audio_mix.py` | **trip** (41) | per-shot overrides |
| Privacy scan (only if asked) | `50_privacy_scan.py [--file f]` | generic | – |

Libraries: `lib_reel.py` (THE decode path, v360 helpers, proxies), `lib_color.py` (OKLab, LUT
I/O, gamut map), `lib_edl.py` (keyframes, easing, crops), `lib_privacy.py` (detectors),
`lib_text.py` (caption design system: 6 styles, adaptive placement + colour, emoji, kinetic pops).

`examples/overlays.csv` + `examples/sfx_cues.csv`: the Kanakapura v7 captions and cues (copy to `assets/`
and rewrite for the trip). Caption copy: emoji where meaningful, no colons.

## Looks
`looks/look2_warm_cinematic.cube` is the standing look. `base_insta360.cube` / `base_samsung.cube` are
the camera matches measured on the Kanakapura footage (`camera_match_stats_kanakapura.json`).
Reuse them for the same cameras in similar light; re-measure with 14/15 otherwise.
Pipeline order per shot: input transform → repair LUT → base_<camera> → look2 → finish LUT.
