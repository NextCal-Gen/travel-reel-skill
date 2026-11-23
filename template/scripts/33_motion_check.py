"""Phase 3/6: motion diagnostic on a RENDERED shot (same thresholds as 11_diagnostics:
needs_ND when median flow > 4 px/frame at 540 px width AND frames still crisp, Laplacian var > 55).
Usage: 33_motion_check.py <shot_id> [win_frames=15]   -> per-window flow / sharpness + trigger."""
import os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb

sid = sys.argv[1]; win = int(sys.argv[2]) if len(sys.argv) > 2 else 15
W, H = 540, 960
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(ROOT, "work", "shots", f"{sid}.mov"), "-vf",
                      to_rgb(W, H, "limited", "rgb24", "area"), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     capture_output=True, check=True).stdout
g = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)]
flow = [float(np.median(np.hypot(*cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 31, 3, 5, 1.1, 0).transpose(2, 0, 1))))
        for a, b in zip(g, g[1:])]
lap = [float(cv2.Laplacian(x, cv2.CV_64F).var()) for x in g]
trig = []
for i in range(0, len(flow), win):
    fw, lw = np.median(flow[i:i + win]), np.median(lap[i:i + win])
    t = fw > 4.0 and lw > 55
    trig.append(t)
    print(f"{sid} frames {i:3d}-{min(i + win, len(flow)):3d}: flow {fw:6.2f} px/frame  lapvar {lw:6.0f}  {'needs_ND TRIGGERED' if t else ''}")
print("TRIGGERED" if any(trig) else "not triggered")
