"""Phase 1.4: write assets/source_inventory.csv.
Technical columns come from assets/metadata_summary.csv and assets/range_vfr_check.csv
(measured). Classification/content/privacy columns come from the visual review of
assets/contact_sheets/*.jpg and assets/range_compare/*.jpg (frames actually viewed)."""
import csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
meta = {r["file"]: r for r in csv.DictReader(open(os.path.join(ROOT, "assets", "metadata_summary.csv")))}
rv = {r["file"]: r for r in csv.DictReader(open(os.path.join(ROOT, "assets", "range_vfr_check.csv")))}

SAMSUNG = "Samsung Galaxy S24 Ultra (SM-S928B)"
INSTA = "Insta360 (X4/X5 inferred from 5.7K60 / 8K30; model not in export metadata)"

# Visual review (contact sheets viewed 2026-11-22). privacy: none/low/medium/HIGH
V = {
 "20261002_095946.mp4": dict(cam=SAMSUNG, type="B flat", content="Temple mandapa entrance (painted ceiling, Nandi, steps) 0-3s; then dark sanctum, priest performing aarti 3.8-13.8s",
     privacy="medium: priest partly visible (dark, side-on); visitors from behind", notes="Sanctum very dark: underexposure diagnostic in Phase 3. Only true-VFR clip."),
 "20261002_101233.mp4": dict(cam=SAMSUNG, type="B flat", content="Static: large naga-hood linga in lily pond, row of small lingas, hills; soft-focus linga in foreground",
     privacy="low: tiny distant figures", notes="Static locked-off shot, good detail/establishing shot."),
 "20261002_103422.mp4": dict(cam=SAMSUNG, type="B flat", content="Static: row of adventure motorcycles parked on hilltop, hazy hills, large sky",
     privacy="low: tiny figures", notes="Visible haze: haze diagnostic in Phase 3. Strong 'ride group' establishing shot."),
 "VID_20261002_100046_00_001_001917.mp4": dict(cam=INSTA, type="A 360 equirect", content="Hilltop viewpoint: red-tiled gazebo, green valley, distant hills; roof fills much of sphere after ~3s",
     privacy="medium: seated visitors under gazebo", notes="Mostly static camera; usable valley-facing directions."),
 "VID_20261002_100141_00_003.mp4": dict(cam=INSTA, type="A 360 equirect", content="Selfie-stick in temple courtyard; stick holder's face large and fully visible entire clip; paved path to shrine",
     privacy="HIGH: holder's face in frame throughout", notes="Different export: tagged full range (correct) and CFR. Only directions facing away from holder usable."),
 "VID_20261002_100158_00_004_002127.mp4": dict(cam=INSTA, type="A 360 equirect", content="Walk along paved temple courtyard toward shrine, gazebo, valley view",
     privacy="medium: holder at frame edge; visitors walking", notes="Forward-walking virtual move possible."),
 "VID_20261002_100322_00_006_002157.mp4": dict(cam=INSTA, type="A 360 equirect", content="Fast walk around temple shrine (rock boulders, gopuram, temple name board) in 2 s",
     privacy="medium: holder visible near bottom", notes="8K 29.97. Motion pace indicates sped-up capture (TimeShift/hyperlapse): judged from motion, not metadata; Phase 7: audio track is digital silence (-240 dBFS), consistent with timelapse capture. Do not speed up further."),
 "VID_20261002_100535_00_008_002614.mp4": dict(cam=INSTA, type="A 360 equirect", content="Lily pond: camera dips to water level, backlit water lilies against sun (hero candidate ~4.4-7s)",
     privacy="medium: holder's face visible at one side throughout", notes="Strongest visual in set. Sun in frame: highlight check in Phase 3."),
 "VID_20261002_100654_00_010_002731.mp4": dict(cam=INSTA, type="A 360 equirect", content="White Nandi statue at head of linga pond; hilltop, visitors",
     privacy="HIGH: other visitors close to camera (woman in blue, others); holder crouching", notes="Nandi-facing direction is clean early in clip."),
 "VID_20261002_100805_00_013_002815.mp4": dict(cam=INSTA, type="A 360 equirect", content="25 s walk around the large linga pond on hilltop; valley and hills behind",
     privacy="HIGH: woman in blue + holder close to camera most of clip", notes="Longest clip; pond-facing direction mostly clean."),
 "VID_20261002_110214_00_015_003301.mp4": dict(cam=INSTA, type="A 360 equirect", content="Riding: bike-mounted, rural road through mango orchards/greenery, hills on horizon",
     privacy="low: rider in full-face helmet, visor down", notes="Bike mount; horizon already levelled by Insta360 (FlowState baked in). Road-ahead direction is the journey shot."),
 "VID_20261002_111449_00_018_003355.mp4": dict(cam=INSTA, type="A 360 equirect", content="Riding through coconut palms, then across a low concrete bridge over the river with a weir/spill (~8-17s)",
     privacy="low: rider in helmet", notes="This is the river crossing on camera: a bridge over the river, not riding through water."),
 "VID_20261002_112312_00_020_003446.mp4": dict(cam=INSTA, type="A 360 equirect", content="Camera on stick over bridge railing: river and weir spill below, road on both sides",
     privacy="HIGH: person in riding jacket on bridge, face visible", notes="River-facing direction is clean."),
 "VID_20261002_112329_00_021_003513.mp4": dict(cam=INSTA, type="A 360 equirect", content="Camera lowered beside bridge toward river: weir spill, water, palms, bridge from below",
     privacy="medium: people on bridge at edges, holder at bottom late in clip", notes="Best river visuals; 0.5-3s low angle on the spill."),
 "VID_20261002_112351_00_022_003538.mp4": dict(cam=INSTA, type="A 360 equirect", content="Selfie on bridge: holder's face large in frame, river and railing behind",
     privacy="HIGH: holder's face in frame throughout", notes="Only river-facing directions usable."),
}

rows = []
for f, v in V.items():
    m, r = meta[f], rv[f]
    is360 = v["type"].startswith("A")
    w, h = m["WxH"].split("x")
    rot = m["rotation"]
    res = f'{m["WxH"]} (stored; rot {rot} -> {h}x{w} portrait)' if rot not in ("", "0", None) else m["WxH"]
    true_vfr = r["true_VFR"] == "True"
    tagged = m["range"]
    full_data = r["uses_full_range"] == "True"
    if is360:
        rng = "full (data 0-255" + (", tagged tv: MIS-TAGGED)" if tagged == "tv" else ", tagged pc: correct)")
    else:
        rng = f"limited (tagged tv; data {r['Ymin_min']}-{r['Ymax_max']}, minor overshoot)"
    conv = []
    if rot not in ("", "0", None): conv.append("apply rotation")
    if is360: conv.append("decode as FULL range" if tagged == "tv" else "decode as full range (as tagged)")
    else: conv.append("decode as limited range (as tagged), keep overshoot")
    conv.append("no colour transform (SDR Rec.709)")
    conv.append("v360 equirect->rectilinear reframe" if is360 else "no dewarp; 9:16 crop")
    if true_vfr: conv.append("conform VFR->CFR 30")
    else: conv.append(f'{m["fps_r"]}->30 fps conform')
    rows.append({
        "filename": f, "camera": v["cam"], "type": v["type"], "resolution": res,
        "fps": m["fps_r"], "VFR": f"yes ({r['irregular_frames']} irregular intervals, {r['frame_dur_min_ms']}-{r['frame_dur_max_ms']} ms)" if true_vfr else "no (CFR timestamps; MediaInfo 'VFR' flag not confirmed)",
        "duration_s": m["duration_s"], "bit_depth": m["bit_depth"], "codec": m["codec"],
        "primaries": m["primaries"], "transfer": m["transfer"], "range": rng,
        "log_hdr_profile": "none: SDR Rec.709 (no HDR side data, no Log signature; normal contrast in viewed frames)",
        "projection": "equirectangular 2:1, stitched by Insta360 Studio (GSpherical metadata)" if is360 else "flat (rectilinear phone lens)",
        "required_conversion": "; ".join(conv),
        "confidence": "high",
        "evidence": ("exiftool StitchingSoftware=Insta360, ProjectionType=equirectangular; ffprobe Spherical Mapping side data; 9 frames viewed; signalstats Ymin 0/Ymax 255"
                     if is360 else
                     "exiftool SamsungModel SM-S928B / Author Galaxy S24 Ultra; ffprobe bt709 8-bit, no HDR side data; 9 frames viewed; tv-vs-pc decode compared"),
        "gyro_data": "none (stripped by Studio export) -> Gyroflow not possible" if is360 else "none",
        "content": v["content"], "privacy_risk": v["privacy"], "notes": v["notes"],
    })
# confidence adjustments
for r in rows:
    if r["filename"] == "VID_20261002_100322_00_006_002157.mp4":
        r["confidence"] = "high (projection/colour); medium (sped-up capture)"
    if r["filename"].startswith("2026"):
        r["confidence"] = "high (camera/projection/SDR); medium-high (range)"

out = os.path.join(ROOT, "assets", "source_inventory.csv")
with open(out, "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
print("wrote", out, len(rows), "clips")
