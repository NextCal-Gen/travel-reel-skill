"""Phase 12b: master + Resolve interchange.
  outputs/travel_reel_MASTER.mov    10-bit ProRes 422 HQ graded timeline (stream copy, no grain)
  outputs/resolve_media/Sxx.mov     graded per-shot ProRes (V1 media)
  outputs/travel_reel.otio          V1 = graded shots; V2 (disabled) = ORIGINAL clips with exact source
                                    in/out + reframe keyframes / LUT chain in clip metadata;
                                    markers = text-overlay plan (assets/overlay_plan.md)
FCPXML: not written (needs the otio-fcp-adapter package, not installed)."""
import os, shutil, subprocess, sys
import opentimelineio as otio
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory
from lib_edl import load_edl

OUT = os.path.join(ROOT, "outputs"); MED = os.path.join(OUT, "resolve_media")
os.makedirs(MED, exist_ok=True)
shutil.copyfile(os.path.join(ROOT, "work", "timeline_prores.mov"), os.path.join(OUT, "travel_reel_MASTER_clean.mov"))
for _top in ("timeline_motion.mov", "timeline_text.mov"):             # motion graphics (70) > captions (93) > clean
    if os.path.exists(os.path.join(ROOT, "work", _top)):
        shutil.copyfile(os.path.join(ROOT, "work", _top), os.path.join(OUT, "travel_reel_MASTER.mov"))
        break
inv = inventory()
RATE = 30
base_lut = {"360": "base_insta360.cube", "flat": "base_samsung.cube"}
repair = {"S02": "repair_S02_dehaze.cube", "S06": "repair_S06_exposure.cube"}
finish = {"S02": "finish_S02_sand.cube"}


def nframes(p):
    return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)


tl = otio.schema.Timeline(name="Kanakapura breakfast ride - travel reel v6")
v1 = otio.schema.Track(name="V1 graded", kind=otio.schema.TrackKind.Video)
v2 = otio.schema.Track(name="V2 originals (reference)", kind=otio.schema.TrackKind.Video)
v2.enabled = False
total = 0
for s in load_edl():
    src = os.path.join(ROOT, "work", "shots", f"{s['id']}.mov"); dst = os.path.join(MED, f"{s['id']}.mov")
    shutil.copyfile(src, dst)
    n = nframes(dst); total += n
    meta = {"travel_reel": {"role": s["role"], "source_clip": s["clip"], "source_in_s": s["tin"], "source_out_s": s["tout"],
                            "kind": s["kind"], "keyframes": s["kf"], "keyframe_format": "[t, yaw, pitch, h_fov]" if s["kind"] == "360" else "[t, zoom, cx, cy]",
                            "motion": s["nd"], "lut_chain": ([] if s["kind"] == "graphic" else ([repair[s["id"]]] if s["id"] in repair else []) + [base_lut[s["kind"]], "look2_warm_cinematic.cube"]
                            + ([finish[s["id"]]] if s["id"] in finish else [])), "repairs": s["repairs"], "privacy": s["privacy"]}}
    v1.append(otio.schema.Clip(name=s["id"], metadata=meta,
                               media_reference=otio.schema.ExternalReference(target_url=f"file://{dst}",
                                   available_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0, RATE), otio.opentime.RationalTime(n, RATE))),
                               source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0, RATE), otio.opentime.RationalTime(n, RATE))))
    if s["kind"] == "graphic":      # generated insert (route map): no original source -> gap on V2
        v2.append(otio.schema.Gap(source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0, RATE),
                                                                      otio.opentime.RationalTime(n, RATE))))
        continue
    sr = float(inv[s["clip"]]["fps"])
    v2.append(otio.schema.Clip(name=f"{s['id']} original", metadata=meta,
                               media_reference=otio.schema.ExternalReference(target_url=f"file://{os.path.join(ROOT, 'raw', s['clip'])}"),
                               source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(round(s["tin"] * sr), sr),
                                                                    otio.opentime.RationalTime(round(n / RATE * sr), sr))))
tl.tracks.append(v1); tl.tracks.append(v2)
# markers = the burned-in captions: assets/overlays.csv (93_text_sfx.py); legacy fallback 92_text_overlays.py OVERLAYS
_csv = os.path.join(ROOT, "assets", "overlays.csv"); OVERLAY = []
if os.path.exists(_csv):
    import csv as _csvm
    OVERLAY = [(float(r["t_in"]), float(r["t_out"]) - float(r["t_in"]), r["text"]) for r in _csvm.DictReader(open(_csv, encoding="utf-8"))]
elif os.path.exists(os.path.join(ROOT, "scripts", "92_text_overlays.py")):
    _src = open(os.path.join(ROOT, "scripts", "92_text_overlays.py")).read()
    _ovl = _src[_src.index("OVERLAYS = ["): _src.index("]\n", _src.index("OVERLAYS = [")) + 1]
    _ns = {}; exec(_ovl, _ns)
    OVERLAY = [(a, b - a, txt) for a, b, txt, _sz, _acc in _ns["OVERLAYS"]]
for t, d, txt in OVERLAY:
    tl.tracks.markers.append(otio.schema.Marker(name=f"CAPTION (burned in): {txt}", marked_range=otio.opentime.TimeRange(
        otio.opentime.RationalTime(round(t * RATE), RATE), otio.opentime.RationalTime(round(d * RATE), RATE)),
        color=otio.schema.MarkerColor.YELLOW))
otio.adapters.write_to_file(tl, os.path.join(OUT, "travel_reel.otio"))
# validate: read back, durations, media present
rt = otio.adapters.read_from_file(os.path.join(OUT, "travel_reel.otio"))
d1 = rt.tracks[0].duration().to_frames()
missing = [c.name for c in rt.tracks[0].find_clips() if not os.path.exists(c.media_reference.target_url[7:])]
missing += [c.name for c in rt.tracks[1].find_clips() if not os.path.exists(c.media_reference.target_url[7:])]
print(f"OTIO V1 {d1} frames (rendered total {total}) ; clips V1 {len(list(rt.tracks[0].find_clips()))} V2 {len(list(rt.tracks[1].find_clips()))} ;"
      f" markers {len(rt.tracks.markers)} ; missing media: {missing or 'none'}")
