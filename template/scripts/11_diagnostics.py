"""Phase 3: measure diagnostics on sampled frames, compare against thresholds, log triggers.
Measured on what the reel will actually show: 9:16 rectilinear views (360 clips: yaw
0/90/180/270, pitch 0, h_fov 70; flat clips: the native 9:16 portrait frame), decoded
through the Phase 2 working-space transform.
Usage: 11_diagnostics.py [--edl | clip ...]   (--edl = only clips in assets/edl.csv)
Outputs: assets/diagnostics.csv (every measurement) and a first-pass trigger list.
Final trigger decisions are made by scripts/12_evaluate_triggers.py, which overwrites
assets/repairs.csv with calibrated, clip-aware rules."""
import csv, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, is360, input_transform, to_rgb, range_of

VW, VH = 540, 960          # analysis view size (9:16)
YAWS = [0, 90, 180, -90]
N_T = 5

# ---- thresholds (documented; working space = display-referred Rec.709, values 0..1) ----
TH = dict(
    clipped_pct=2.0,          # % pixels with any channel >= 0.995
    contrast_p95_p5=0.85,     # with shadow_pct below
    shadow_pct=12.0,          # % pixels with Y < 0.06
    under_mean_Y=0.22,        # mean luma of the view
    haze_dark_channel=0.28,   # mean dark channel (15 px patch) below the horizon band, with low contrast
    haze_contrast_max=0.55,
    wb_a=3.0, wb_b=5.0,       # |mean a*|, |mean b*| of near-neutral pixels (Lab)
    noise_sigma=3.0,          # Immerkaer sigma on 8-bit scale
    shake_jitter_px=1.2,      # residual global motion std, px at 540 wide, per 30p frame
    nd_flow_px=4.0,           # median flow px/frame at 30p, 540 wide ...
    nd_sharp_lapvar=60.0,     # ... AND frames still crisp (Laplacian variance)
    banding_smooth_sky_pct=15.0,
)


def decode_equirect(path, t, row, w=2048):
    vf = input_transform(row) + "," + to_rgb(w, w // 2, range_of(row), "rgb24", "area")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                          "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(w // 2, w, 3)


def decode_flat(path, t, row):
    vf = input_transform(row) + "," + to_rgb(VW, VH, range_of(row), "rgb24", "area")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                          "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(VH, VW, 3)


_maps = {}
def view(eq, yaw, pitch=0, h_fov=70):
    """Equirect -> rectilinear remap (analysis only; final renders use ffmpeg v360)."""
    key = (eq.shape, yaw, pitch, h_fov)
    if key not in _maps:
        H, W = eq.shape[:2]
        f = (VW / 2) / np.tan(np.radians(h_fov / 2))
        x, y = np.meshgrid(np.arange(VW) - VW / 2 + 0.5, np.arange(VH) - VH / 2 + 0.5)
        d = np.stack([x, -y, np.full_like(x, f)], -1)
        d /= np.linalg.norm(d, axis=-1, keepdims=True)
        p, yw = np.radians(pitch), np.radians(yaw)
        Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
        Ry = np.array([[np.cos(yw), 0, np.sin(yw)], [0, 1, 0], [-np.sin(yw), 0, np.cos(yw)]])
        d = d @ (Ry @ Rx).T
        lon = np.arctan2(d[..., 0], d[..., 2]); lat = np.arcsin(np.clip(d[..., 1], -1, 1))
        _maps[key] = (((lon / np.pi + 1) / 2 * W - 0.5).astype(np.float32),
                      ((0.5 - lat / np.pi) * H - 0.5).astype(np.float32))
    mx, my = _maps[key]
    return cv2.remap(eq, mx, my, cv2.INTER_AREA, borderMode=cv2.BORDER_WRAP)


def luma(rgb):  # rgb float 0..1, Rec.709 coefficients on gamma-encoded values (video Y')
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def still_metrics(img8):
    rgb = img8.astype(np.float32) / 255
    Y = luma(rgb)
    m = {}
    m["clipped_pct"] = float((rgb.max(-1) >= 0.995).mean() * 100)
    p5, p95 = np.percentile(Y, [5, 95])
    m["p5"], m["p95"], m["contrast_p95_p5"] = float(p5), float(p95), float(p95 - p5)
    m["shadow_pct"] = float((Y < 0.06).mean() * 100)
    m["mean_Y"] = float(Y.mean())
    # haze: dark channel on lower 60% of the view (landscape band; sky excluded mostly)
    band = rgb[int(VH * 0.4):]
    dc = cv2.erode(band.min(-1), np.ones((15, 15), np.uint8))
    yb = luma(band); m["haze_dark_channel"] = float(dc.mean())
    m["band_contrast"] = float(np.percentile(yb, 95) - np.percentile(yb, 5))
    # WB: near-neutral, mid-tone pixels in Lab
    lab = cv2.cvtColor(img8, cv2.COLOR_RGB2LAB).astype(np.float32)
    L, a, b = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    neutral = (np.hypot(a, b) < 10) & (L > 25) & (L < 92)
    m["neutral_pct"] = float(neutral.mean() * 100)
    m["wb_a"] = float(a[neutral].mean()) if neutral.sum() > 2000 else float("nan")
    m["wb_b"] = float(b[neutral].mean()) if neutral.sum() > 2000 else float("nan")
    # noise: Immerkaer estimator on 8-bit luma
    g = (Y * 255).astype(np.float64)
    M = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float64)
    conv = cv2.filter2D(g, -1, M)[1:-1, 1:-1]
    m["noise_sigma"] = float(np.sqrt(np.pi / 2) * np.abs(conv).sum() / (6 * (g.shape[1] - 2) * (g.shape[0] - 2)))
    # banding risk: smooth, bright, bluish (sky) area fraction
    grad = cv2.Laplacian(g, cv2.CV_64F)
    sky = (rgb[..., 2] > rgb[..., 0] + 0.05) & (Y > 0.45) & (np.abs(grad) < 1.5)
    m["smooth_sky_pct"] = float(sky.mean() * 100)
    m["lapvar"] = float(cv2.Laplacian(g, cv2.CV_64F).var())
    return m


def motion_metrics(path, row, t0, yaw):
    """1 s of frames at native rate, take every source frame that maps to 30p, flow per frame."""
    fps = float(row["fps"]); step = max(1, round(fps / 30))
    n = int(fps)  # 1 second
    if is360(row):
        vf = input_transform(row) + "," + to_rgb(1440, 720, range_of(row), "rgb24", "area"); w, h = 1440, 720
    else:
        vf = input_transform(row) + "," + to_rgb(VW, VH, range_of(row), "rgb24", "area"); w, h = VW, VH
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", path, "-frames:v", str(n),
                          "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)[::step]
    if is360(row):
        fr = np.stack([view(f, yaw) for f in fr])
    gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in fr]
    mags, gx, gy = [], [], []
    for a, b in zip(gray, gray[1:]):
        flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 21, 3, 5, 1.1, 0)
        mags.append(float(np.median(np.hypot(flow[..., 0], flow[..., 1]))))
        gx.append(float(np.median(flow[..., 0]))); gy.append(float(np.median(flow[..., 1])))
    tr = np.cumsum(np.stack([gx, gy], 1), 0)
    k = 7
    sm = np.stack([np.convolve(np.pad(tr[:, i], k // 2, mode="edge"), np.ones(k) / k, mode="valid") for i in range(2)], 1)
    jitter = float(np.linalg.norm(tr - sm, axis=1).std()) if len(tr) > k else 0.0
    lap = float(np.median([cv2.Laplacian(g, cv2.CV_64F).var() for g in gray]))
    return dict(flow_px=float(np.median(mags)), jitter_px=jitter, lapvar_motion=lap)


inv = inventory()
# --edl: measure only clips used by the edit list (pick shots first, then diagnose: saves time).
# Explicit clip names on the command line also work. Default: every clip.
if "--edl" in sys.argv:
    import csv as _csv
    _used = {r["clip"] for r in _csv.DictReader(open(os.path.join(ROOT, "assets", "edl.csv"))) if r.get("kind") != "graphic"}
    inv = {c: r for c, r in inv.items() if c in _used}
elif len(sys.argv) > 1:
    inv = {c: r for c, r in inv.items() if c in sys.argv[1:]}
print(f"diagnosing {len(inv)} clip(s)")
diag, repairs = [], []
for clip, row in inv.items():
    path = os.path.join(ROOT, "raw", clip)
    dur = float(row["duration_s"])
    times = [dur * (i + 0.5) / N_T for i in range(N_T)]
    yaws = YAWS if is360(row) else [None]
    per_view = {y: [] for y in yaws}
    for t in times:
        if is360(row):
            eq = decode_equirect(path, t, row)
            for y in yaws:
                per_view[y].append(still_metrics(view(eq, y)))
        else:
            per_view[None].append(still_metrics(decode_flat(path, t, row)))
    for y in yaws:
        ms = per_view[y]
        agg = {k: float(np.nanmedian([m[k] for m in ms])) for k in ms[0]}
        agg["clipped_pct_max"] = float(max(m["clipped_pct"] for m in ms))
        agg["mean_Y_min"] = float(min(m["mean_Y"] for m in ms))
        mot = motion_metrics(path, row, min(max(0.0, dur / 2 - 0.5), max(0.0, dur - 1.1)), y or 0)
        agg.update(mot)
        rec = {"clip": clip, "view": ("yaw%+d" % y) if y is not None else "full 9:16", **{k: round(v, 3) for k, v in agg.items()}}
        diag.append(rec)

        def trig(name, value, thr, action, why):
            repairs.append({"clip": clip, "view": rec["view"], "diagnostic": name, "value": round(value, 3),
                            "threshold": thr, "action_if_selected": action, "why": why})
        if agg["clipped_pct"] > TH["clipped_pct"]:
            trig("clipped_highlights", agg["clipped_pct"], f'>{TH["clipped_pct"]}%', "highlight roll-off (soft shoulder); clipped data not recoverable",
                 "median % pixels with a channel at max")
        if agg["contrast_p95_p5"] > TH["contrast_p95_p5"] and agg["shadow_pct"] > TH["shadow_pct"]:
            trig("harsh_contrast", agg["contrast_p95_p5"], f'>{TH["contrast_p95_p5"]} & shadows>{TH["shadow_pct"]}%',
                 "gentle shadow lift + soft-knee highlights", f'shadow_pct={agg["shadow_pct"]:.1f}')
        if agg["mean_Y"] < TH["under_mean_Y"]:
            trig("underexposure", agg["mean_Y"], f'<{TH["under_mean_Y"]}', "exposure lift before grade (check noise after)", "median mean luma of view")
        if agg["haze_dark_channel"] > TH["haze_dark_channel"] and agg["band_contrast"] < TH["haze_contrast_max"]:
            trig("haze", agg["haze_dark_channel"], f'>{TH["haze_dark_channel"]} & contrast<{TH["haze_contrast_max"]}',
                 "mild dehaze / local contrast on this shot only", f'band_contrast={agg["band_contrast"]:.2f}')
        if not np.isnan(agg["wb_a"]) and (abs(agg["wb_a"]) > TH["wb_a"] or abs(agg["wb_b"]) > TH["wb_b"]):
            trig("wb_cast", max(abs(agg["wb_a"]), abs(agg["wb_b"])), f'|a*|>{TH["wb_a"]} or |b*|>{TH["wb_b"]}',
                 "WB correction toward neutral (verify visually: sunlit warmth may be intended)", f'a*={agg["wb_a"]:.1f} b*={agg["wb_b"]:.1f}')
        if agg["noise_sigma"] > TH["noise_sigma"]:
            trig("noise", agg["noise_sigma"], f'>{TH["noise_sigma"]}', "temporal denoise (hqdn3d) before grade", "Immerkaer sigma (includes fine texture)")
        if agg["jitter_px"] > TH["shake_jitter_px"]:
            trig("shake", agg["jitter_px"], f'>{TH["shake_jitter_px"]}px', "vidstab (no gyro data available)", "residual global motion std")
        if agg["flow_px"] > TH["nd_flow_px"] and agg["lapvar_motion"] > TH["nd_sharp_lapvar"]:
            trig("needs_ND", agg["flow_px"], f'flow>{TH["nd_flow_px"]}px & lapvar>{TH["nd_sharp_lapvar"]}',
                 "ND emulation: blend 60p frame pairs (~180deg shutter at 30p); RIFE only if source is 30p",
                 f'lapvar={agg["lapvar_motion"]:.0f}')
        if row["bit_depth"] == "8" and agg["smooth_sky_pct"] > TH["banding_smooth_sky_pct"]:
            trig("banding_risk", agg["smooth_sky_pct"], f'8-bit & smooth sky>{TH["banding_smooth_sky_pct"]}%',
                 "limit sky secondaries; fine grain at export", "smooth bright bluish area fraction")
    print(f"done {clip}")

for name, rows in (("diagnostics.csv", diag), ("repairs.csv", repairs)):
    with open(os.path.join(ROOT, "assets", name), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(diag), "views measured;", len(repairs), "triggers")
