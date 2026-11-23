"""Phase 3/6: build per-shot repair LUTs for TRIGGERED repairs only (see assets/repairs.csv),
then measure the effect on the shot's own frames and log it to assets/repairs_applied.csv.
  S02 dehaze_mild    : haze model I = J*t + A*(1-t) inverted with constant t in linear light;
                       A (airlight) measured from this shot's sky; t chosen mild.
  S06 exposure_lift  : linear-light gain + soft shoulder on OKLab L (lamps don't hard-clip);
                       noise re-measured after the lift (diagnostic asked for it).
Pipeline position: after the input transform, before base/look LUTs."""
import csv, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, grab_rgb
from lib_color import to_lin, to_disp, rgb_to_oklab, oklab_to_rgb, lch, from_lch, soft_shoulder, write_cube, read_cube, apply_cube, gamut_map
from lib_edl import load_edl, interp, flat_crop

LK = os.path.join(ROOT, "assets", "looks")
edl = {s["id"]: s for s in load_edl()}


def shot_frame(sid, rel=None):
    s = edl[sid]; rel = s["dur"] / 2 if rel is None else rel
    full = grab_rgb(s["clip"], s["tin"] + rel, "", 2160, 3840)
    z, cx, cy = interp(s["kf"], rel)
    x, y, w, h = flat_crop(2160, 3840, z, cx, cy)
    return cv2.resize(full[y:y + h, x:x + w], (540, 960), interpolation=cv2.INTER_AREA)


def dark_channel_band(rgb):
    band = rgb[int(rgb.shape[0] * 0.4):]
    return float(cv2.erode(band.min(-1), np.ones((15, 15), np.uint8)).mean())


def noise_sigma(rgb):
    g = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) * 255
    M = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float64)
    c = cv2.filter2D(g.astype(np.float64), -1, M)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(c).sum() / (6 * (g.shape[1] - 2) * (g.shape[0] - 2)))


log = []
# ---- S02 mild dehaze -------------------------------------------------------------------
f = shot_frame("S02")
sky = f[: int(f.shape[0] * 0.30)].reshape(-1, 3)
A_lin = to_lin(np.percentile(sky, 90, axis=0))          # bright haze/sky colour (linear)
T = 0.90   # mild: removes ~10% veil. (v1 used 0.86: near sand went orange after base+look -> reduced)


def dehaze(rgb):
    lin = to_lin(rgb)
    J = (lin - A_lin[None, :] * (1 - T)) / T
    return to_disp(np.clip(J, 0, None))


write_cube(os.path.join(LK, "repair_S02_dehaze.cube"), dehaze, title="S02 mild dehaze")
g = apply_cube(f, read_cube(os.path.join(LK, "repair_S02_dehaze.cube")))
Yb = lambda im: 0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]
band_c = lambda im: float(np.percentile(Yb(im[int(im.shape[0] * .4):]), 95) - np.percentile(Yb(im[int(im.shape[0] * .4):]), 5))
log.append(dict(shot="S02", repair="dehaze_mild", trigger="dark channel 0.417 > 0.28, band contrast 0.50 < 0.55 (confirmed visually)",
                params=f"t={T}, airlight(lin)={np.round(A_lin, 3).tolist()}",
                before=f"dark_channel={dark_channel_band(f):.3f} band_contrast={band_c(f):.3f}",
                after=f"dark_channel={dark_channel_band(g):.3f} band_contrast={band_c(g):.3f}",
                file="assets/looks/repair_S02_dehaze.cube"))
cv2.imwrite(os.path.join(ROOT, "assets", "diag_views", "_repair_S02.jpg"),
            (np.hstack([f, g]) * 255).clip(0, 255).astype(np.uint8)[..., ::-1])

# ---- S06 exposure lift -----------------------------------------------------------------
f = shot_frame("S06")
STOPS = 1.3


def lift(rgb):
    lin = to_lin(rgb) * 2 ** STOPS
    L, C, h = lch(rgb_to_oklab(np.clip(to_disp(lin), 0, 4)))
    L2 = soft_shoulder(L, knee=0.78, white=0.98)
    C2 = C * np.where(L > 1e-4, np.clip(L2 / np.maximum(L, 1e-4), 0, 1), 1)  # keep saturation in check where compressed
    return np.clip(oklab_to_rgb(from_lch(L2, gamut_map(L2, C2, h), h)), 0, 1)


write_cube(os.path.join(LK, "repair_S06_exposure.cube"), lift, n=65, title="S06 exposure lift")
g = apply_cube(f, read_cube(os.path.join(LK, "repair_S06_exposure.cube")))
nb, na = noise_sigma(f), noise_sigma(g)
log.append(dict(shot="S06", repair="exposure_lift", trigger="mean Y 0.108 < 0.22",
                params=f"+{STOPS} stops linear, OKLab shoulder knee 0.78",
                before=f"mean_Y={Yb(f).mean():.3f} noise_sigma={nb:.2f} clip%={(f.max(-1) >= .995).mean() * 100:.2f}",
                after=f"mean_Y={Yb(g).mean():.3f} noise_sigma={na:.2f} clip%={(g.max(-1) >= .995).mean() * 100:.2f}"
                      + (" -> NOISE TRIGGER (>3.0): temporal denoise required" if na > 3.0 else " -> noise below 3.0, no denoise"),
                file="assets/looks/repair_S06_exposure.cube"))
cv2.imwrite(os.path.join(ROOT, "assets", "diag_views", "_repair_S06.jpg"),
            (np.hstack([f, g]) * 255).clip(0, 255).astype(np.uint8)[..., ::-1])

with open(os.path.join(ROOT, "assets", "repairs_applied.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(log[0].keys())); w.writeheader(); w.writerows(log)
for r in log: print(r["shot"], r["repair"], "|", r["before"], "->", r["after"])
