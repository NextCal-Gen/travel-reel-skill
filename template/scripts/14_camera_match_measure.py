"""Phase 4.1: measure camera rendering differences on matched content.
Samsung 101233 (10:12) and Insta360 100535 (10:05) show the same lily pond / naga linga in
the same light. Regions are selected by colour/brightness masks (viewpoints differ, so no
pixel correspondence): clear sky, cloud, dark stone, lily-pad green. Plus a broader sample
of all Samsung outdoor clips vs all Insta360 views for global tone statistics.
Output: assets/camera_match_stats.json"""
import json, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, grab_rgb, v360_view, inventory

inv = inventory()


def lab_of(rgb):
    return cv2.cvtColor((np.clip(rgb, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)


def regions(rgb):
    lab = lab_of(rgb); L = lab[..., 0] * 100 / 255; a = lab[..., 1] - 128; b = lab[..., 2] - 128
    C = np.hypot(a, b); h = np.degrees(np.arctan2(b, a)) % 360
    H = rgb.shape[0]; top = np.zeros(L.shape, bool); top[: int(H * 0.45)] = True
    masks = {
        "clear_sky": top & (b < -8) & (L > 45) & (L < 92),
        "cloud":     top & (L > 82) & (C < 12),
        "dark_stone": (L > 8) & (L < 35) & (C < 8),
        "green":     (h > 95) & (h < 160) & (C > 12) & (L > 25),
    }
    out = {}
    for k, m in masks.items():
        if m.sum() < 300:
            out[k] = None; continue
        out[k] = dict(px=int(m.sum()), L=float(L[m].mean()), a=float(a[m].mean()), b=float(b[m].mean()),
                      C=float(C[m].mean()), hue=float(np.degrees(np.arctan2(b[m].mean(), a[m].mean())) % 360),
                      rgb=[float(x) for x in rgb[m].mean(0)])
    Y = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    out["tone"] = dict(p2=float(np.percentile(Y, 2)), p50=float(np.percentile(Y, 50)), p98=float(np.percentile(Y, 98)),
                       chroma_med=float(np.median(C)), chroma_p90=float(np.percentile(C, 90)))
    return out


res = {}
# matched scene
res["samsung_pond"] = regions(grab_rgb("20261002_101233.mp4", 2.0, "", 540, -2))
res["insta_pond"] = regions(grab_rgb("VID_20261002_100535_00_008_002614.mp4", 0.6, v360_view(15, 0, 0, 50, 540, 960), 540, 960))
# broader: Samsung outdoor clips (2) and Insta360 non-sun views across clips (yaw 90/180 at 3 times)
sam, ins = [], []
for c, t in (("20261002_101233.mp4", 1.0), ("20261002_101233.mp4", 3.5), ("20261002_103422.mp4", 1.0), ("20261002_103422.mp4", 4.5)):
    sam.append(regions(grab_rgb(c, t, "", 540, -2)))
for c in ["VID_20261002_100046_00_001_001917.mp4", "VID_20261002_100158_00_004_002127.mp4",
          "VID_20261002_100805_00_013_002815.mp4", "VID_20261002_110214_00_015_003301.mp4",
          "VID_20261002_111449_00_018_003355.mp4", "VID_20261002_112329_00_021_003513.mp4"]:
    d = float(inv[c]["duration_s"])
    for yaw in (0, 90):
        ins.append(regions(grab_rgb(c, d * 0.5, v360_view(yaw, 0, 0, 70, 540, 960), 540, 960)))


def agg(lst, key, field):
    v = [r[key][field] for r in lst if r.get(key)]
    return float(np.median(v)) if v else None


for name, lst in (("samsung_all", sam), ("insta_all", ins)):
    res[name] = {k: {f: agg(lst, k, f) for f in ("L", "a", "b", "C", "hue")} for k in ("clear_sky", "cloud", "dark_stone", "green")}
    res[name]["tone"] = {f: float(np.median([r["tone"][f] for r in lst])) for f in ("p2", "p50", "p98", "chroma_med", "chroma_p90")}

json.dump(res, open(os.path.join(ROOT, "assets", "camera_match_stats.json"), "w"), indent=1)
for k in ("samsung_pond", "insta_pond", "samsung_all", "insta_all"):
    print("==", k)
    for reg, v in res[k].items():
        if v is None: print(f"  {reg:10s} (too few px)"); continue
        print("  %-10s " % reg + " ".join(f"{f}={v[f]:.2f}" for f in v if isinstance(v.get(f), (int, float)) and v[f] is not None))
