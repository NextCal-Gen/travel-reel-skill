"""Phase 11: automated QC of a render. Usage: 61_qc.py <file.mp4> [reference_prores.mov] [--target MIN MAX]
Runs (and reports only what actually ran):
  duration (ffprobe) vs the target range (default 18-25 s, --target MIN MAX) / 30 s hard max; stream format checks
  location metadata: exiftool finds no GPS / ISO6709 / location tags
  blackdetect, freezedetect, flash frames (single-frame luma spikes from signalstats)
  signalstats: out-of-legal-range luma (<16 / >235) and frames with clipped highlights
  VMAF + SSIM vs the graded ProRes timeline (encode fidelity), if a reference is given
  loudness (ebur128 integrated / true peak) and A/V duration/start alignment
  1-fps contact sheet for visual review
Output: assets/qc_<name>.json, assets/qc_<name>_sheet.jpg"""
import json, os, re, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb

args = [a for a in sys.argv[1:]]
target = (18.0, 25.0)
if "--target" in args:                       # per-reel range from the plan, e.g. --target 12 18
    i = args.index("--target"); target = (float(args[i + 1]), float(args[i + 2])); del args[i:i + 3]
f = args[0]; ref = args[1] if len(args) > 1 else None
name = os.path.splitext(os.path.basename(f))[0]
R = {"file": f}


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


# --- format / duration
pr = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", f]).stdout)
v = next(s for s in pr["streams"] if s["codec_type"] == "video"); a = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
dur = float(pr["format"]["duration"])
R["duration_s"] = dur
R["duration_target_s"] = list(target)
R["duration_ok"] = target[0] <= dur <= target[1]
R["under_hard_max_30s"] = dur <= 30
R["video"] = {k: v.get(k) for k in ("codec_name", "profile", "width", "height", "pix_fmt", "r_frame_rate", "avg_frame_rate",
                                    "color_range", "color_primaries", "color_transfer", "color_space")}
R["audio"] = {k: a.get(k) for k in ("codec_name", "sample_rate", "channels", "bit_rate")} if a else None
R["av_alignment"] = dict(video_start=float(v.get("start_time", 0)), audio_start=float(a.get("start_time", 0)) if a else None,
                         video_dur=float(v.get("duration", 0)), audio_dur=float(a.get("duration", 0)) if a else None)
R["av_alignment"]["dur_diff_ms"] = (round(abs(R["av_alignment"]["video_dur"] - R["av_alignment"]["audio_dur"]) * 1000, 1)
                                    if a else "n/a: no audio stream")

# --- location metadata: nothing GPS-like may survive into a deliverable
ex = run(["exiftool", "-j", "-a", "-G1", "-ee", "-api", "LargeFileSupport=1", f])
if ex.returncode == 0 and ex.stdout.strip():
    tags = json.loads(ex.stdout)[0]
    gps = sorted(k for k in tags if re.search(r"GPS|ISO6709|Location", k, re.I))
    R["gps_metadata_tags"] = gps
    R["gps_metadata_ok"] = not gps
else:
    R["gps_metadata_ok"] = "not checked: exiftool unavailable"

# --- black / freeze
e = run(["ffmpeg", "-hide_banner", "-i", f, "-vf", "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=0.001:d=0.5", "-an", "-f", "null", "-"]).stderr
R["blackdetect"] = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", e)
R["freezedetect"] = re.findall(r"freeze_start: ([\d.]+)", e)

# --- per-frame signalstats (flash frames) + direct pixel count of out-of-legal-range luma
e = run(["ffmpeg", "-hide_banner", "-i", f, "-vf", "signalstats,metadata=print:file=-", "-an", "-f", "null", "-"]).stdout
def series(key): return np.array([float(x) for x in re.findall(rf"lavfi\.signalstats\.{key}=([\d.]+)", e)])
yavg, ymin, ymax = series("YAVG"), series("YMIN"), series("YMAX")
d1 = np.diff(yavg)
R["frames"] = int(len(yavg))
R["flash_frames"] = [int(i + 1) for i in range(len(d1) - 1) if abs(d1[i]) > 12 and abs(d1[i + 1]) > 12 and np.sign(d1[i]) != np.sign(d1[i + 1])]
R["luma_min_overall"], R["luma_max_overall"] = float(ymin.min()), float(ymax.max())
W_, H_ = int(v["width"]), int(v["height"])
pp = subprocess.Popen(["ffmpeg", "-v", "error", "-i", f, "-vf", "extractplanes=y", "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
lo = hi = tot = 0
while True:
    buf = pp.stdout.read(W_ * H_)
    if len(buf) < W_ * H_: break
    yy = np.frombuffer(buf, np.uint8); lo += int((yy < 16).sum()); hi += int((yy > 235).sum()); tot += yy.size
R["pixels_below_16_pct"] = round(lo / tot * 100, 4); R["pixels_above_235_pct"] = round(hi / tot * 100, 4)
R["legal_range_ok"] = lo == 0 and hi == 0

# --- VMAF / SSIM vs reference (graded ProRes timeline)
if ref:
    e = run(["ffmpeg", "-hide_banner", "-i", f, "-i", ref, "-lavfi",
             "[0:v]setpts=PTS-STARTPTS,format=yuv420p[d];[1:v]setpts=PTS-STARTPTS,scale=in_range=tv:out_range=tv,format=yuv420p[r];"
             "[d]split[d1][d2];[r]split[r1][r2];[d1][r1]libvmaf=n_threads=8:log_fmt=json:log_path=/dev/null[o1];[d2][r2]ssim[o2]",
             "-map", "[o1]", "-f", "null", "-", "-map", "[o2]", "-f", "null", "-"]).stderr
    m = re.search(r"VMAF score: ([\d.]+)", e); s = re.search(r"SSIM .*All:([\d.]+)", e)
    R["vmaf_vs_graded_master"] = float(m.group(1)) if m else None
    R["ssim_vs_graded_master"] = float(s.group(1)) if s else None

# --- loudness
if a is None:
    R["loudness_LUFS"] = R["true_peak_dBTP"] = None
    R["loudness_ok"] = "n/a: no audio stream (muted by request)"
else:
  e = run(["ffmpeg", "-hide_banner", "-i", f, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
  summ = e[e.rfind("Summary:"):]
  I = re.search(r"I:\s+(-?[\d.]+) LUFS", summ); TP = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ)
  R["loudness_LUFS"] = float(I.group(1)) if I else None
  R["true_peak_dBTP"] = float(TP.group(1)) if TP else None
  R["loudness_ok"] = R["loudness_LUFS"] is not None and abs(R["loudness_LUFS"] + 14) <= 1.0 and R["true_peak_dBTP"] <= -1.0 + 0.05

# --- 1 fps contact sheet
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", "fps=1," + to_rgb(216, 384, "limited", "rgb24"),
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 384, 216, 3)
tiles = []
for i, t in enumerate(fr):
    t = t[..., ::-1].copy(); cv2.rectangle(t, (0, 0), (216, 16), (0, 0, 0), -1)
    cv2.putText(t, f"{i:02d}s", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1); tiles.append(t)
while len(tiles) % 8: tiles.append(np.zeros_like(tiles[0]))
sheet = np.vstack([np.hstack(tiles[i:i + 8]) for i in range(0, len(tiles), 8)])
cv2.imwrite(os.path.join(ROOT, "assets", f"qc_{name}_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
json.dump(R, open(os.path.join(ROOT, "assets", f"qc_{name}.json"), "w"), indent=1)
print(json.dumps(R, indent=1))
