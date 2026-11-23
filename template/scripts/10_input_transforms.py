"""Phase 2: input transforms into the working space (Rec.709 / BT.1886 SDR).
For every clip:
  - record the ffmpeg input-transform chain in assets/transforms.json
  - render a before/after still: BEFORE = decoded exactly as the file is tagged,
    AFTER = decoded with the working-space transform (lib_reel.input_transform)
  - report the mean absolute difference so 'no-op' transforms are visible as such
Output: assets/transforms/<clip>.jpg, assets/transforms/overview_*.jpg, assets/transforms.json"""
import json, os, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, is360, input_transform, to_rgb48, range_of, save_jpg
import subprocess, re

OUT = os.path.join(ROOT, "assets", "transforms")
os.makedirs(OUT, exist_ok=True)


def decode(clip, t, chain, w, rng):
    p = os.path.join(ROOT, "raw", clip)
    vf = (chain + "," if chain else "") + to_rgb48(w, -2, rng)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", p, "-frames:v", "1",
                          "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
                         capture_output=True, check=True).stdout
    h = len(raw) // (w * 3 * 2)
    return np.frombuffer(raw, "<u2").reshape(h, w, 3).astype(np.float32) / 65535


inv = inventory()
record, tiles = {}, []
for clip, row in inv.items():
    t = float(row["duration_s"]) * 0.45
    w = 1200 if is360(row) else 540
    tag_rng = "full" if "tagged pc" in row["range"] else "limited"
    before = decode(clip, t, "", w, tag_rng)                          # as the file is tagged
    after = decode(clip, t, input_transform(row), w, range_of(row))   # working space
    diff = float(np.abs(after - before).mean())
    clipped_b = float((before.max(axis=2) >= 0.999).mean() * 100)
    clipped_a = float((after.max(axis=2) >= 0.999).mean() * 100)
    crushed_b = float((before.max(axis=2) <= 0.001).mean() * 100)
    crushed_a = float((after.max(axis=2) <= 0.001).mean() * 100)
    record[clip] = dict(chain=input_transform(row), sample_t=round(t, 2),
                        mean_abs_diff=round(diff, 4),
                        clipped_pct_before=round(clipped_b, 2), clipped_pct_after=round(clipped_a, 2),
                        crushed_pct_before=round(crushed_b, 2), crushed_pct_after=round(crushed_a, 2),
                        note=("range override pc (file tagged tv)" if (row["range"].startswith("full") and "MIS-TAGGED" in row["range"])
                              else "no-op: decoded as tagged"))
    pair = np.hstack([before, np.ones((before.shape[0], 8, 3), np.float32), after]) if not is360(row) \
        else np.vstack([before, np.ones((8, before.shape[1], 3), np.float32), after])
    img = (np.clip(pair, 0, 1) * 255).astype(np.uint8)[..., ::-1].copy()
    lab = f"{clip[:24]}  BEFORE(as tagged) | AFTER  diff={diff:.3f}  clip%%={clipped_b:.1f}->{clipped_a:.1f}"
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), (0, 0, 0), -1)
    cv2.putText(img, lab.replace("%%", "%"), (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(os.path.join(OUT, os.path.splitext(clip)[0] + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"{clip:42s} diff={diff:.4f} clipped {clipped_b:.2f}->{clipped_a:.2f}%  crushed {crushed_b:.2f}->{crushed_a:.2f}%")

json.dump(record, open(os.path.join(ROOT, "assets", "transforms.json"), "w"), indent=1)
