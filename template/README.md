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
| Route map (optional) | `90_fetch_osm.sh`, `91_route_map.py` | **trip** (91; bbox in 90) | `PTS` pins, routes, labels, bbox |
| On-screen text (optional) | `92_text_overlays.py <ver>` | **trip** | `OVERLAYS` (times on the current timeline) |
| Rough cut | `60_assemble.py <ver> --mute` → `61_qc.py <file> [master]` | generic | – |
| 🛑 Gate 3 (user checks faces on the rough cut) | | | |
| Finishing | `70_shot_match.py` → `71_finishing_trims.py` | **trip** | ground regions; trims for measured outliers |
| Export | `80_export.py <out> [--master work/timeline_text.mov]` | generic | – |
| Master + Resolve | `81_export_master_otio.py` | **trip** | timeline name |
| Audio (only if asked) | `40_audio_analysis.py`, `41_audio_mix.py` | **trip** (41) | per-shot overrides |
| Privacy scan (only if asked) | `50_privacy_scan.py [--file f]` | generic | – |

Libraries: `lib_reel.py` (THE decode path, v360 helpers, proxies), `lib_color.py` (OKLab, LUT
I/O, gamut map), `lib_edl.py` (keyframes, easing, crops), `lib_privacy.py` (detectors).

## Looks
`looks/look2_warm_cinematic.cube` is the standing look. `base_insta360.cube` / `base_samsung.cube` are
the camera matches measured on the Kanakapura footage (`camera_match_stats_kanakapura.json`).
Reuse them for the same cameras in similar light; re-measure with 14/15 otherwise.
Pipeline order per shot: input transform → repair LUT → base_<camera> → look2 → finish LUT.
