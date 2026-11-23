"""Phase 5.2: shot-selection material.
 - 360 clips: 6 directions (yaw 0/60/120/180/240/300, pitch -5, h_fov 70, 9:16) x 1 frame per second.
 - flat clips: 9:16 frame x 2 per second.
Every tile (540x960) is scanned with YuNet faces + YOLO persons. Tile border: RED = face found,
ORANGE = near person (box height > 35% of frame) without face, none = clear.
Outputs: assets/direction_sheets/<clip>.jpg, assets/person_map.csv"""
import csv, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, is360, equirect_view, proxy_frames
from lib_privacy import faces, persons

OUT = os.path.join(ROOT, "assets", "direction_sheets"); os.makedirs(OUT, exist_ok=True)
YAWS = [0, 60, 120, 180, 240, 300]
TW, TH = 180, 320
inv = inventory()
only = sys.argv[1:]
rows_csv = []
for clip, row in inv.items():
    if only and clip not in only:
        continue
    dur = float(row["duration_s"])
    sheet_rows = []
    if is360(row):
        frames = proxy_frames(clip, 0.25, dur - 0.3, 1, 2880, 1440)
        views = lambda eq: [(y, equirect_view(eq, y, -5, 70, 540, 960)) for y in YAWS]
    else:
        frames = proxy_frames(clip, 0.25, dur - 0.3, 2, 540, 960)
        views = lambda im: [("flat", im)]
    for t, fr in frames:
        tiles = []
        for yaw, v in views(fr):
            F = faces(v); P = persons(v)
            near = [p for p in P if p[3] > 0.35 * 960]
            maxface = max([f[2] for f in F], default=0)
            rows_csv.append(dict(clip=clip, t=round(t, 2), yaw=yaw, faces=len(F), max_face_px=int(maxface),
                                 persons=len(P), near_persons=len(near),
                                 max_person_h=int(max([p[3] for p in P], default=0))))
            tile = cv2.resize(v, (TW, TH), interpolation=cv2.INTER_AREA)[..., ::-1].copy()
            col = (0, 0, 255) if F else ((0, 140, 255) if near else None)
            if col: cv2.rectangle(tile, (0, 0), (TW - 1, TH - 1), col, 6)
            lab = f"{t:4.1f}s y{yaw}" if yaw != "flat" else f"{t:4.1f}s"
            cv2.rectangle(tile, (0, 0), (TW, 18), (0, 0, 0), -1)
            cv2.putText(tile, lab + (" FACE" if F else ""), (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
            tiles.append(tile)
        sheet_rows.append(np.hstack(tiles))
    if not is360(row):   # wrap flat clips into rows of 8
        flat = [t for r in sheet_rows for t in [r]]
        while len(flat) % 8: flat.append(np.zeros_like(flat[0]))
        sheet_rows = [np.hstack(flat[i:i + 8]) for i in range(0, len(flat), 8)]
    cv2.imwrite(os.path.join(OUT, os.path.splitext(clip)[0] + ".jpg"), np.vstack(sheet_rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
    print("sheet", clip, len(sheet_rows), "rows")

path = os.path.join(ROOT, "assets", "person_map.csv")
mode = "a" if only and os.path.exists(path) else "w"
with open(path, mode, newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_csv[0].keys()))
    if mode == "w": w.writeheader()
    w.writerows(rows_csv)
