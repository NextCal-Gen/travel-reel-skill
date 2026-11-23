"""v7: B-roll candidates from 360 clips - one 360 clip holds many usable angles.
Scans every 360 clip (originals, working-space decode) every 2 s at 12 yaws x 3 pitches with the
narrowest field of view that needs NO upscaling (h_fov >= 1080 / (equirect_width / 360)).
Score = colourfulness (Hasler-Suesstrunk) + detail (edge density) - sky dominance - clipping.
Privacy rule (user, v7): ONLY the camera holder must never appear; passers-by are fine.
Holder direction per clip is MEASURED from assets/person_map.csv (21_direction_sheets: 6 yaws x 1 fps): the
yaws whose median largest-person height is >= 150 px (circular mean, weighted). Views within +-75 deg of it are
skipped; +-100 deg when the holder is in >= 90% of samples (bike mount / stick very close: hands and
handlebars reach further round). Fallback when a clip has no data: holder at 180 +-75. Then each pick is
checked with YOLO at t-0.5, t, t+0.5 s and rejected only for a CLOSE person (the holder next to the stick:
box >= 40% of the view height, or touching the bottom edge and >= 22% wide) or a close motorcycle
(own bike / handlebars in the foreground, >= 30% of the view height: a framing-quality rule).
Also excluded: sun-facing views (> 8% clipped) and moments already used in the edit (assets/edl.csv).
Diversity: <= 2 per clip, yaw spread, <= 4 downward views.
Output: assets/broll_candidates.csv, assets/broll_sheet.jpg (graded with base + Look 2)."""
import csv, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, is360, grab_rgb, equirect_view
from lib_color import read_cube, apply_cube

inv = inventory()
LK = os.path.join(ROOT, "assets", "looks")
luts = [read_cube(os.path.join(LK, n)) for n in ("base_insta360.cube", "look2_warm_cinematic.cube")]
edl = list(csv.DictReader(open(os.path.join(ROOT, "assets", "edl.csv"))))
YAWS, PITCHES = list(range(0, 360, 30)), [-30, 0, 15]
PM = [r for r in csv.DictReader(open(os.path.join(ROOT, "assets", "person_map.csv"))) if r["yaw"] != "flat"]


def holder_zone(clip):
    """(centre_yaw, half_width) of the camera holder's direction, measured from the person map."""
    rows = [r for r in PM if r["clip"] == clip]
    ys = sorted({int(r["yaw"]) for r in rows}); wsum = np.zeros(2); near_max = 0.0
    for y in ys:
        rr = [r for r in rows if int(r["yaw"]) == y]
        h = float(np.median([float(r["max_person_h"]) for r in rr]))
        if h >= 150:
            wsum += h * np.array([np.cos(np.radians(y)), np.sin(np.radians(y))])
            near_max = max(near_max, float(np.mean([int(r["near_persons"]) > 0 for r in rr])))
    if not wsum.any(): return 180.0, 75.0
    return float(np.degrees(np.arctan2(wsum[1], wsum[0])) % 360), (100.0 if near_max >= 0.9 else 75.0)


def colourfulness(rgb):
    r, g, b = rgb[..., 0] * 255, rgb[..., 1] * 255, rgb[..., 2] * 255
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def used(clip, t):
    return any(r["clip"] == clip and float(r["tin"]) - 0.5 <= t <= float(r["tout"]) + 0.5 for r in edl)


def angdiff(a, b): return abs((a - b + 180) % 360 - 180)


cands = []
for clip, row in inv.items():
    if not is360(row): continue
    eq_w = int(row["resolution"].split("x")[0]); hfov = float(np.ceil(1080 / (eq_w / 360) + 0.5))
    dur = float(row["duration_s"]); hz = holder_zone(clip)
    print(f"{clip[13:19]} holder at yaw {hz[0]:.0f} +-{hz[1]:.0f}")
    for t in np.arange(0.5, dur - 0.4, 2.0):
        if used(clip, t): continue
        eq = (grab_rgb(clip, float(t), "", 2880, 1440, row=row) * 255).astype(np.uint8)
        for yaw in YAWS:
            if angdiff(yaw, hz[0]) <= hz[1]: continue
            for pitch in PITCHES:
                v = equirect_view(eq, yaw, pitch, hfov, 270, 480).astype(np.float32) / 255
                clip_pct = float((v.max(-1) >= 0.99).mean() * 100)
                if clip_pct > 8: continue
                g = cv2.cvtColor((v * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
                edges = float((cv2.Canny(g, 60, 140) > 0).mean() * 100)
                sky = float(((v[..., 2] > v[..., 0] + 0.06) & (v.mean(-1) > 0.55)).mean())
                score = colourfulness(v) * 0.6 + edges * 2.0 - max(sky - 0.45, 0) * 120 - clip_pct * 2
                cands.append(dict(clip=clip, t=round(float(t), 2), yaw=yaw, pitch=pitch, h_fov=hfov, score=round(score, 1),
                                  colourfulness=round(colourfulness(v), 1), edges_pct=round(edges, 1), sky=round(sky, 2),
                                  clipped_pct=round(clip_pct, 1)))
    print(f"scanned {clip}: {sum(1 for c in cands if c['clip'] == clip)} candidate views")

# Selection: best first, <= 2 per clip, yaw spread, <= 4 downward views, then the holder check on the view itself.
from ultralytics import YOLO
yolo = YOLO(os.path.join(os.environ.get("TRAVEL_REEL_MODELS", os.path.expanduser("~/travel-reel-toolkit/models")), "yolo11n.pt"))
VW, VH = 540, 960


def close_subject(c):
    """Reason string if the camera holder (close person) or own bike shows in the view around c['t'], else None."""
    for dt in (-0.5, 0.0, 0.5):
        t = min(max(c["t"] + dt, 0.0), float(inv[c["clip"]]["duration_s"]) - 0.1)
        eq = (grab_rgb(c["clip"], t, "", 2880, 1440) * 255).astype(np.uint8)
        v = equirect_view(eq, c["yaw"], c["pitch"], c["h_fov"], VW, VH)
        det = yolo.predict(v[..., ::-1], conf=0.25, classes=[0, 3], verbose=False, imgsz=640)[0].boxes
        for b, k in zip(det.xyxy.tolist(), det.cls.tolist()):
            h, w = (b[3] - b[1]) / VH, (b[2] - b[0]) / VW
            if k == 0 and (h >= 0.40 or (b[3] >= 0.97 * VH and w >= 0.22)): return f"holder (close person) t{t:.1f}"
            if k == 3 and h >= 0.30: return f"own bike in foreground t{t:.1f}"
    return None


cands.sort(key=lambda c: -c["score"]); pick = []; rejected = []
for c in cands:
    same = [p for p in pick if p["clip"] == c["clip"]]
    if len(same) >= 2 or any(angdiff(p["yaw"], c["yaw"]) < 60 for p in same): continue
    if c["pitch"] < 0 and sum(p["pitch"] < 0 for p in pick) >= 4: continue
    why = close_subject(c)
    if why:
        rejected.append((c["clip"][13:19], c["t"], c["yaw"], c["pitch"], why)); continue
    pick.append(c)
    if len(pick) == 12: break
for r in rejected: print("rejected", r)
print(f"rejected {len(rejected)} candidate views (holder / own bike)")
with open(os.path.join(ROOT, "assets", "broll_candidates.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(pick[0].keys())); w.writeheader(); w.writerows(pick)
tiles = []
for c in pick:
    eq = (grab_rgb(c["clip"], c["t"], "", 2880, 1440) * 255).astype(np.uint8)
    v = equirect_view(eq, c["yaw"], c["pitch"], c["h_fov"], 360, 640).astype(np.float32) / 255
    v = apply_cube(apply_cube(v, luts[0]), luts[1])
    im = (np.clip(v, 0, 1) * 255).astype(np.uint8)[..., ::-1].copy()
    cv2.rectangle(im, (0, 0), (360, 22), (0, 0, 0), -1)
    cv2.putText(im, f"{c['clip'][13:19]} t{c['t']} y{c['yaw']} p{c['pitch']} s{c['score']}", (5, 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    tiles.append(im)
while len(tiles) % 6: tiles.append(np.full_like(tiles[0], 30))
sheet = np.vstack([np.hstack([np.pad(t, ((3, 3), (3, 3), (0, 0)), constant_values=255) for t in tiles[i:i + 6]]) for i in range(0, len(tiles), 6)])
cv2.imwrite(os.path.join(ROOT, "assets", "broll_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
for p in pick: print(p)
