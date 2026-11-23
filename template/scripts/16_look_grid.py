"""Phase 4.3: render the look-candidate grid and verify the base match.
Rows: representative 9:16 frames (Samsung pond linga; Insta360 lily pond; Insta360 riding).
Cols: working space (Phase 2 only) | base match | look1 | look2 | look3.
Also: (a) re-measure neutrals/chroma after base match (convergence check),
      (b) render one tile through ffmpeg lut3d and compare with the Python LUT path.
Output: assets/look_candidates.png, assets/looks/base_match_report.json"""
import json, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, input_transform, v360_view, grab_rgb, save_png16, to_working_rgb, range_of
from lib_color import read_cube, apply_cube

LK = os.path.join(ROOT, "assets", "looks")
inv = inventory()
W, H = 540, 960
SHOTS = [
    ("Samsung S24U", "20261002_101233.mp4", 2.0, None, "base_samsung"),
    ("Insta360 lily pond", "VID_20261002_100535_00_008_002614.mp4", 5.66, (18, 20, 70), "base_insta360"),
    ("Insta360 riding", "VID_20261002_110214_00_015_003301.mp4", 4.2, (0, -3, 75), "base_insta360"),
]
LOOKS = ["look1_natural", "look2_warm_cinematic", "look3_filmic"]
luts = {n: read_cube(os.path.join(LK, n + ".cube")) for n in ["base_samsung", "base_insta360"] + LOOKS}


def frame(clip, t, v):
    if v:
        return grab_rgb(clip, t, v360_view(v[0], v[1], 0, v[2], W, H), W, H)
    return grab_rgb(clip, t, "", W, H)


def label(img, text):
    im = (np.clip(img, 0, 1) * 255).astype(np.uint8)[..., ::-1].copy()
    cv2.rectangle(im, (0, H - 34), (W, H), (0, 0, 0), -1)
    cv2.putText(im, text, (8, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    return im


def neutrals(rgb):
    lab = cv2.cvtColor((np.clip(rgb, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255; a = lab[..., 1] - 128; b = lab[..., 2] - 128; C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360
    top = np.zeros(L.shape, bool); top[: int(H * 0.45)] = True
    def m(mask):
        return None if mask.sum() < 200 else dict(a=round(float(a[mask].mean()), 2), b=round(float(b[mask].mean()), 2),
                                                  C=round(float(C[mask].mean()), 2), px=int(mask.sum()))
    return dict(cloud=m(top & (L > 82) & (C < 14)), stone=m((L > 8) & (L < 35) & (C < 9)),
                sky=m(top & (b < -8) & (L > 45) & (L < 92)), green=m((h > 95) & (h < 160) & (C > 12) & (L > 25)),
                chroma_median=round(float(np.median(C)), 2))


from lib_color import rgb_to_oklab


def look_stats(rgb):
    lab = rgb_to_oklab(np.clip(rgb, 0, 1).reshape(-1, 3))
    L, C = lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])
    return dict(contrast_L_p95_p5=round(float(np.percentile(L, 95) - np.percentile(L, 5)), 3),
                warmth_mean_b=round(float(lab[:, 2].mean() * 100), 2),
                chroma_median=round(float(np.median(C) * 100), 2),
                black_p1=round(float(np.percentile(L, 1)), 3), white_p99=round(float(np.percentile(L, 99)), 3))


rows, report = [], {}
for name, clip, t, v, base in SHOTS:
    src = frame(clip, t, v)
    b = apply_cube(src, luts[base])
    graded = {l: apply_cube(b, luts[l]) for l in LOOKS}
    tiles = [label(src, f"{name}: source (working space)"), label(b, "base match")]
    tiles += [label(graded[l], l.replace("_", " ")) for l in LOOKS]
    rows.append(np.hstack([np.pad(x, ((0, 0), (0, 6), (0, 0)), constant_values=255) for x in tiles]))
    report[name] = dict(before=neutrals(src), after_base=neutrals(b),
                        look_stats={"base": look_stats(b), **{l: look_stats(g) for l, g in graded.items()}})
grid = np.vstack([np.pad(r, ((0, 6), (0, 0), (0, 0)), constant_values=255) for r in rows])
cv2.imwrite(os.path.join(ROOT, "assets", "look_candidates.png"), grid, [cv2.IMWRITE_PNG_COMPRESSION, 6])

# ffmpeg lut3d consistency check on the riding tile, look2
name, clip, t, v, base = SHOTS[2]
chain = (input_transform(inv[clip]) + "," + v360_view(v[0], v[1], 0, v[2], W, H) +
         "," + to_working_rgb(range_of(inv[clip])) + f",lut3d=file={LK}/{base}.cube:interp=trilinear,lut3d=file={LK}/look2_warm_cinematic.cube:interp=trilinear")
raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", os.path.join(ROOT, "raw", clip), "-frames:v", "1",
                      "-vf", chain + ",format=rgb48le", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
                     capture_output=True, check=True).stdout
ff = np.frombuffer(raw, "<u2").reshape(H, W, 3).astype(np.float32) / 65535
py = apply_cube(apply_cube(frame(clip, t, v), luts[base]), luts["look2_warm_cinematic"])
report["ffmpeg_vs_python_lut_mean_abs_diff_8bit"] = round(float(np.abs(ff - py).mean() * 255), 3)
report["ffmpeg_vs_python_lut_p99_abs_diff_8bit"] = round(float(np.percentile(np.abs(ff - py), 99) * 255), 3)
json.dump(report, open(os.path.join(LK, "base_match_report.json"), "w"), indent=1)
print(json.dumps(report, indent=1))
