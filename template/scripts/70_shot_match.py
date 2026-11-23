"""Phase 10.1: shot-to-shot colour consistency of the graded shots (work/shots/*.mov).
Per shot (5 frames): OKLab mean L, median chroma, warmth (mean b), plus a 'ground' region check:
bottom 25% of frames where the ground is sand/dirt/paving -> chroma and hue, to compare the S02 sand
against other sunlit ground in the reel. Output: assets/shot_match.csv"""
import csv, glob, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb
from lib_color import rgb_to_oklab
from lib_edl import load_edl

W, H = 270, 480
GROUND = {"S02": "sand", "S03": "paving", "S08": "dirt path (lower-left)", "S10": "dusty road/bridge deck"}
rows = []
for s in load_edl():
    f = os.path.join(ROOT, "work", "shots", f"{s['id']}.mov")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", "fps=2," + to_rgb(W, H, "limited", "rgb48le", "area"),
                          "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, "<u2").reshape(-1, H, W, 3).astype(np.float32) / 65535
    lab = rgb_to_oklab(fr.reshape(-1, 3)); C = np.hypot(lab[:, 1], lab[:, 2])
    g = rgb_to_oklab(fr[:, int(H * 0.75):].reshape(-1, 3)); gC = np.hypot(g[:, 1], g[:, 2])
    gh = np.degrees(np.arctan2(np.median(g[:, 2]), np.median(g[:, 1]))) % 360
    rows.append(dict(shot=s["id"], L_mean=round(float(lab[:, 0].mean()), 3), chroma_med=round(float(np.median(C)) * 100, 2),
                     warmth_b=round(float(lab[:, 2].mean()) * 100, 2), ground=GROUND.get(s["id"], ""),
                     ground_chroma_med=round(float(np.median(gC)) * 100, 2), ground_hue=round(float(gh), 1)))
with open(os.path.join(ROOT, "assets", "shot_match.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(r)
