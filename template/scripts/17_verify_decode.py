"""Regression test for every decode path (run after any change to lib_reel decode code).
Ground truth: untouched Y/Cb/Cr code values (extractplanes, no range conversion) converted by hand
with BT.709 equations for the range established in Phase 1. Checked paths:
  render  = lib_reel.grab_rgb (input_transform + zscale working RGB)   <- previews AND final renders
  proxy   = 20_proxies.sh chain (to limited 10-bit) decoded back with the proxy path
Pass criteria target RANGE/MATRIX errors, not interpolation noise (the hand path scales the
half-res chroma planes separately, which alone costs ~1-2/255 mean |diff|):
  |mean signed diff| per channel < 1.0/255  AND  |p1|,|p99| luma shift < 2/255  AND  mean |diff| < 3/255.
A single range squeeze shows up as ~6-9/255 shift and ~15-20/255 p1/p99 movement."""
import os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, input_transform, range_of, grab_rgb, to_rgb

W, H = 720, 360
CASES = [("VID_20261002_100141_00_003.mp4", 2.0),   # yuvj420p, tagged pc (correct)
         ("VID_20261002_100535_00_008_002614.mp4", 2.0),  # yuv420p, tagged tv, data full
         ("20261002_101233.mp4", 2.0)]                # Samsung yuv420p tv, rotated


def manual(clip, t, rng, w, h):
    planes = []
    for p in ("y", "u", "v"):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", f"{ROOT}/raw/{clip}", "-frames:v", "1",
                              "-vf", f"extractplanes={p},scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        planes.append(np.frombuffer(raw, np.uint8).reshape(h, w).astype(np.float64))
    Y, Cb, Cr = planes
    if rng == "full":
        y, cb, cr = Y / 255, (Cb - 128) / 255, (Cr - 128) / 255
    else:
        y, cb, cr = (Y - 16) / 219, (Cb - 128) / 224, (Cr - 128) / 224
    return np.clip(np.stack([y + 1.5748 * cr, y - 0.1873 * cb - 0.4681 * cr, y + 1.8556 * cb], -1), 0, 1)


def via_proxy_chain(clip, t, row, w, h):
    enc = (input_transform(row) + f",zscale=w={w}:h={h}:filter=lanczos:rangein={range_of(row)}:range=limited:"
           "matrixin=709:matrix=709:primariesin=709:primaries=709:transferin=709:transfer=709,format=p010le")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", f"{ROOT}/raw/{clip}", "-frames:v", "1", "-vf", enc,
                    "-c:v", "ffv1", f"{ROOT}/work/_proxytest.mkv"], check=True)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"{ROOT}/work/_proxytest.mkv", "-frames:v", "1", "-vf", to_rgb(w, h, "limited"),
                          "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"], capture_output=True, check=True).stdout
    os.remove(f"{ROOT}/work/_proxytest.mkv")
    return np.frombuffer(raw, "<u2").reshape(h, w, 3).astype(np.float64) / 65535


inv = inventory(); ok = True
for clip, t in CASES:
    row = inv[clip]
    rot = clip.startswith("2026")
    w, h = (360, 640) if rot else (W, H)
    # ffmpeg autorotates BEFORE the filter graph, so extractplanes already sees the portrait frame
    gt = manual(clip, t, range_of(row), w, h)
    r = grab_rgb(clip, t, "", w, h, row=row)
    p = via_proxy_chain(clip, t, row, w, h)
    def check(x):
        Y = lambda im: 0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]
        mad = np.abs(x - gt).mean() * 255
        shift = np.abs((x - gt).mean((0, 1)) * 255).max()
        dp = max(abs(np.percentile(Y(x), q) - np.percentile(Y(gt), q)) * 255 for q in (1, 99))
        return mad, shift, dp, (mad < 3 and shift < 1.0 and dp < 2.0)
    res = {k: check(x) for k, x in (("render", r), ("proxy", p))}
    ok &= all(v[3] for v in res.values())
    print(f"{clip[:36]:36s} " + " | ".join(f"{k}: mad {v[0]:4.2f} shift {v[1]:4.2f} p1/p99 {v[2]:4.2f} {'PASS' if v[3] else 'FAIL'}" for k, v in res.items()))
print("ALL PASS" if ok else "FAILURES PRESENT")
sys.exit(0 if ok else 1)
