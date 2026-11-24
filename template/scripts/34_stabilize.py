"""Phase 3 shake repair for flat shots when neither Gyroflow (no gyro data) nor vidstab (not in this ffmpeg
build) is available: measure frame-to-frame translation on the 10-bit proxy (phase correlation, 540 wide),
smooth the camera path (gaussian, sigma 0.35 s, --sigma=S to change), and write per-frame crop offsets that 30_render_shot.py
adds to the crop window (needs zoom headroom: >= 1.10 on the shot).
Usage: 34_stabilize.py S06 [...]   Output: assets/stab/<id>.json  {"fps": f, "dx": [...], "dy": [...]} in SOURCE px"""
import json, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, proxy_frames
from lib_edl import load_edl

PW, PH, SRC_W = 540, 960, 2160
SIGMA_S = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--sigma=")), 0.35))   # seconds; smaller = remove only fast jitter
os.makedirs(os.path.join(ROOT, "assets", "stab"), exist_ok=True)
inv = inventory()
for s in load_edl():
    if s["id"] not in sys.argv[1:]:
        continue
    fps = float(inv[s["clip"]]["fps"])
    pad = 0.4                                                   # context either side so the smoothing has no edge effect
    t0 = max(0.0, s["tin"] - pad)
    frames = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32)
              for _, f in proxy_frames(s["clip"], t0, s["dur"] + 2 * pad, fps, PW, PH)]
    win = cv2.createHanningWindow((PW, PH), cv2.CV_32F)
    traj = [np.zeros(2)]
    for a, b in zip(frames, frames[1:]):
        (dx, dy), _ = cv2.phaseCorrelate(a, b, win)
        traj.append(traj[-1] + [dx, dy])
    traj = np.array(traj)
    sig = SIGMA_S * fps
    k = np.exp(-0.5 * (np.arange(-3 * sig, 3 * sig + 1) / sig) ** 2); k /= k.sum()
    padded = np.pad(traj, ((len(k) // 2, len(k) // 2), (0, 0)), mode="edge")
    smooth = np.stack([np.convolve(padded[:, i], k, mode="valid") for i in range(2)], 1)[: len(traj)]
    off = (traj - smooth) * (SRC_W / PW)                       # move the crop WITH the shake -> content stays put
    i0 = int(round((s["tin"] - t0) * fps))
    off = off[i0:]
    jit_before = np.diff(traj, axis=0).std(0); jit_after = np.diff(smooth, axis=0).std(0)
    json.dump({"fps": fps, "dx": off[:, 0].round(2).tolist(), "dy": off[:, 1].round(2).tolist()},
              open(os.path.join(ROOT, "assets", "stab", f"{s['id']}.json"), "w"))
    print(f"{s['id']}: frame-step std {jit_before.round(2)} -> {jit_after.round(2)} px (540 wide); "
          f"max offset {np.abs(off).max(0).round(0)} src px")
