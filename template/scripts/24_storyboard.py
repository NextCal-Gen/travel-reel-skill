"""Phase 5.5: storyboard of the EDL: first / middle / last frame of every shot, from proxies,
with base + Look 2 applied (approved at Gate 2), so framing and grade can be checked before
the full-quality render. Output: assets/storyboard.jpg"""
import os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, equirect_view, proxy_frames
from lib_color import read_cube, apply_cube
from lib_edl import load_edl, interp, flat_crop

LK = os.path.join(ROOT, "assets", "looks")
luts = {n: read_cube(os.path.join(LK, n + ".cube")) for n in ("base_insta360", "base_samsung", "look2_warm_cinematic")}
TW, TH = 270, 480
cols = []
for s in load_edl():
    tiles = []
    for rel in (0.05, s["dur"] / 2, s["dur"] - 0.05):
        t = s["tin"] + rel
        if s["kind"] == "360":
            eq = next(proxy_frames(s["clip"], t, 0.04, 30, 2880, 1440))[1]
            yaw, pitch, hf = interp(s["kf"], rel)
            v = equirect_view(eq, yaw, pitch, hf, TW * 2, TH * 2)
            base = "base_insta360"
        else:
            fr = next(proxy_frames(s["clip"], t, 0.04, 30, 1080, 1920))[1]
            z, cx, cy = interp(s["kf"], rel)
            x, y, w, h = flat_crop(1080, 1920, z, cx, cy)
            v = cv2.resize(fr[y:y + h, x:x + w], (TW * 2, TH * 2), interpolation=cv2.INTER_AREA)
            base = "base_samsung"
        g = apply_cube(apply_cube(v.astype(np.float32) / 255, luts[base]), luts["look2_warm_cinematic"])
        tile = cv2.resize((np.clip(g, 0, 1) * 255).astype(np.uint8), (TW, TH), interpolation=cv2.INTER_AREA)[..., ::-1].copy()
        cv2.rectangle(tile, (0, 0), (TW, 18), (0, 0, 0), -1)
        cv2.putText(tile, f"{s['id']} +{rel:.1f}s", (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        tiles.append(tile)
    cols.append(np.vstack(tiles))
board = np.hstack([np.pad(c, ((0, 0), (0, 4), (0, 0)), constant_values=255) for c in cols])
cv2.imwrite(os.path.join(ROOT, "assets", "storyboard.jpg"), board, [cv2.IMWRITE_JPEG_QUALITY, 85])
print("storyboard", board.shape)
