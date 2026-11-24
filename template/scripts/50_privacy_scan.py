"""Phase 8: privacy scan of EVERY frame of the rendered shots (what the reel actually shows).
Detectors: YuNet faces (score >= 0.6, native + 2x upscale for small faces) and YOLO11n persons.
Policy:
  face width >= 24 px (on the 1080x1920 frame)  -> IDENTIFIABLE -> must be reframed / trimmed / excluded
  face width <  24 px                           -> logged as non-identifiable (distant)
  person box height > 35% of frame              -> near person -> visual review
Every face detection is also saved as a crop for visual review: assets/privacy_crops/
Can scan rendered shots (default) or a finished file:  50_privacy_scan.py [--file path.mp4]
Output: assets/privacy_report.csv (one row per frame with any detection) + summary per shot."""
import csv, glob, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb
from lib_privacy import faces, persons

W, H = 1080, 1920
IDENT_PX = 24
CROPS = os.path.join(ROOT, "assets", "privacy_crops"); os.makedirs(CROPS, exist_ok=True)


def frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", to_rgb(W, H, "limited", "rgb24"),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    i = 0
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3: break
        yield i, np.frombuffer(buf, np.uint8).reshape(H, W, 3); i += 1


if "--file" in sys.argv:
    targets = [("FINAL", sys.argv[sys.argv.index("--file") + 1])]
    report = os.path.join(ROOT, "assets", "privacy_report_final.csv")
else:
    targets = [(os.path.basename(f)[:-4], f) for f in sorted(glob.glob(os.path.join(ROOT, "work", "shots", "*.mov")))]
    report = os.path.join(ROOT, "assets", "privacy_report.csv")

rows, summary = [], []
for sid, path in targets:
    nfr = ident = small = near = 0
    for i, fr in frames(path):
        nfr += 1
        F = faces(fr); P = persons(fr)
        nearP = [p for p in P if p[3] > 0.35 * H]
        if not F and not nearP: continue
        idf = [f for f in F if f[2] >= IDENT_PX]
        ident += bool(idf); small += bool(F and not idf); near += bool(nearP)
        for k, (x, y, w, h, sc) in enumerate(F):
            if i % 5 == 0 or w >= IDENT_PX:   # crops: every identifiable hit, 1 in 5 frames for small ones
                pad = int(max(w, h) * 1.5)
                c = fr[max(0, int(y) - pad): int(y + h) + pad, max(0, int(x) - pad): int(x + w) + pad]
                if c.size:
                    cv2.imwrite(os.path.join(CROPS, f"{sid}_f{i:04d}_{k}_w{int(w)}_s{sc:.2f}.jpg"),
                                cv2.resize(c, (160, int(160 * c.shape[0] / max(c.shape[1], 1))))[..., ::-1])
        rows.append(dict(shot=sid, frame=i, t=round(i / 30, 3), faces=len(F),
                         face_widths=" ".join(str(int(f[2])) for f in F), face_scores=" ".join(f"{f[4]:.2f}" for f in F),
                         identifiable=len(idf), near_persons=len(nearP),
                         person_heights=" ".join(str(int(p[3])) for p in P)))
    summary.append(dict(shot=sid, frames=nfr, frames_identifiable_face=ident, frames_small_face=small, frames_near_person=near))
    print(f"{sid}: {nfr} frames | identifiable-face frames {ident} | small-face frames {small} | near-person frames {near}")

with open(report, "w", newline="") as fh:
    if rows:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    else:
        fh.write("no detections\n")
with open(report.replace(".csv", "_summary.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
