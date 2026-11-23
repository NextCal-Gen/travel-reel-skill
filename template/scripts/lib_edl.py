"""EDL helpers shared by storyboard (24) and shot renderer (30)."""
import csv, json, os
import numpy as np
from lib_reel import ROOT

OUT_W, OUT_H = 1080, 1920


def load_edl():
    with open(os.path.join(ROOT, "assets", "edl.csv")) as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["tin"], r["tout"], r["dur"] = float(r["tin"]), float(r["tout"]), float(r["dur"])
        r["kf"] = json.loads(r["keyframes"])
    return rows


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def interp(kf, t):
    """Smoothstep-eased interpolation of keyframe vectors at relative time t."""
    kf = sorted(kf, key=lambda k: k[0])
    if t <= kf[0][0]:
        return list(kf[0][1:])
    for a, b in zip(kf, kf[1:]):
        if a[0] <= t <= b[0]:
            u = ease((t - a[0]) / max(b[0] - a[0], 1e-9))
            return [va + (vb - va) * u for va, vb in zip(a[1:], b[1:])]
    return list(kf[-1][1:])


def vfov(h_fov, w=OUT_W, h=OUT_H):
    return float(np.degrees(2 * np.arctan(np.tan(np.radians(h_fov / 2)) * h / w)))


def flat_crop(src_w, src_h, zoom, cx, cy):
    """9:16 crop window (x, y, w, h) in source pixels for a flat portrait source."""
    w = src_w / zoom; h = src_h / zoom
    x = np.clip(cx * src_w - w / 2, 0, src_w - w); y = np.clip(cy * src_h - h / 2, 0, src_h - h)
    return int(round(x)), int(round(y)), int(round(w)) // 2 * 2, int(round(h)) // 2 * 2
