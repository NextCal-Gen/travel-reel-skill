"""Cut check from the FINAL render (not the shot files): for every cut, the last frame before and the
first frame after, side by side, plus flags. Catches what a 1 fps contact sheet misses: a caption or
graphic hanging over into the next shot, a stray frame, a black frame, a cut that didn't happen.

Usage: 62_cut_check.py <render.mp4|.mov> [--out assets/cut_check.jpg]
Cut positions come from the EDL order and each work/shots/<id>.mov frame count (same as 60_assemble)."""
import json, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_edl import load_edl

src = sys.argv[1]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "assets", "cut_check.jpg")


def nframes(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    return int(r)


shots = load_edl()
cuts, n = [], 0
for s in shots[:-1]:
    n += nframes(os.path.join(ROOT, "work", "shots", f"{s['id']}.mov"))
    cuts.append((s["id"], n))
total = nframes(src)
W, H = 1080, 1920
want = sorted({f for _, c in cuts for f in (c - 1, c) if 0 <= f < total})
frames = {}
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf",
                      "select='" + "+".join(f"eq(n\\,{f})" for f in want) + "',scale=360:640",
                      "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
for f in want:
    b = p.stdout.read(360 * 640 * 3)
    if len(b) < 360 * 640 * 3:
        break
    frames[f] = np.frombuffer(b, np.uint8).reshape(640, 360, 3)
p.wait()
rows, rep = [], []
for (sid, c), nxt in zip(cuts, shots[1:]):
    a, b = frames.get(c - 1), frames.get(c)
    if a is None or b is None:
        rep.append(dict(cut=c, after=sid, flag="frame missing in render")); continue
    flags = []
    if b.mean() < 8 or a.mean() < 8:
        flags.append("black frame at cut")
    if np.abs(a.astype(np.int16) - b.astype(np.int16)).mean() < 2.0:
        flags.append("no visible change: cut missing or duplicated frame")
    rep.append(dict(cut_frame=c, time=round(c / 30, 3), before=sid, after=nxt["id"], flags=flags))
    pair = np.hstack([a, np.full((640, 8, 3), 255, np.uint8), b])
    cv2.putText(pair, f"{sid} | {nxt['id']}  f{c}  {c / 30:.2f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 0, 255) if flags else (255, 255, 255), 2)
    rows.append(pair)
if total != n + nframes(os.path.join(ROOT, "work", "shots", f"{shots[-1]['id']}.mov")):
    rep.append(dict(flag=f"render has {total} frames, shots add up to a different count (trimmed or padded?)"))
grid = []
for i in range(0, len(rows), 3):
    r = rows[i:i + 3]
    while len(r) < 3:
        r.append(np.zeros_like(rows[0]))
    grid.append(np.hstack(r))
os.makedirs(os.path.dirname(out), exist_ok=True)
if grid:
    cv2.imwrite(out, np.vstack(grid), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(json.dumps(dict(sheet=out, cuts=len(cuts), flagged=[r for r in rep if r.get("flags") or r.get("flag")]), indent=1))
