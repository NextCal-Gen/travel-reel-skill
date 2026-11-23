"""Phase 1.3: verify two metadata flags that can't be trusted blindly.
 - Range: measure actual luma min/max over sampled frames (signalstats) to see whether
   a 'pc'/full-range tagged clip really uses 0-255, and whether 'tv' clips stay in 16-235.
 - VFR: measure frame-duration spread from packet timestamps (first 600 frames).
Output: assets/range_vfr_check.csv"""
import csv, glob, json, os, subprocess, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for path in sorted(glob.glob(os.path.join(ROOT, "raw", "*.mp4"))):
    name = os.path.basename(path)
    # --- range: signalstats on 1 frame every ~0.5 s, raw decoded values (no scaling)
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf",
         "fps=2,scale=960:-2:flags=neighbor:in_range=tv:out_range=tv,signalstats,"
         "metadata=print:key=lavfi.signalstats.YMIN:file=-,"
         "metadata=print:key=lavfi.signalstats.YMAX:file=-",
         "-f", "null", "-"], capture_output=True, text=True).stdout
    ymin = [float(l.split("=")[1]) for l in out.splitlines() if "YMIN=" in l]
    ymax = [float(l.split("=")[1]) for l in out.splitlines() if "YMAX=" in l]
    # --- VFR: packet pts deltas
    j = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#600",
         "-show_entries", "packet=pts_time", "-of", "json", path]))
    pts = sorted(float(p["pts_time"]) for p in j["packets"] if p.get("pts_time") not in (None, "N/A"))
    d = [b - a for a, b in zip(pts, pts[1:]) if b > a]
    med = statistics.median(d)
    irregular = sum(1 for x in d if abs(x - med) > 0.25 * med)
    rows.append({
        "file": name,
        "Ymin_min": min(ymin), "Ymin_p50": statistics.median(ymin),
        "Ymax_max": max(ymax), "Ymax_p50": statistics.median(ymax),
        "uses_full_range": (min(ymin) < 12 or max(ymax) > 240),
        "frame_dur_median_ms": round(med * 1000, 3),
        "frame_dur_min_ms": round(min(d) * 1000, 3), "frame_dur_max_ms": round(max(d) * 1000, 3),
        "irregular_frames": irregular, "frames_checked": len(d),
        "true_VFR": irregular > 0,
    })
    print(name, rows[-1]["Ymin_min"], rows[-1]["Ymax_max"], med * 1000, irregular)

with open(os.path.join(ROOT, "assets", "range_vfr_check.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
