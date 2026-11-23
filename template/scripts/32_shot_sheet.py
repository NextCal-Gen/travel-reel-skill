"""Phase 6 QC: contact sheet of the RENDERED shots (first / middle / last frame of each
work/shots/<id>.mov, decoded with the standard limited-range path). Output: assets/shots_sheet.jpg"""
import glob, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb

TW, TH = 270, 480
cols = []
for f in sorted(glob.glob(os.path.join(ROOT, "work", "shots", "S*.mov"))):
    n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", f], capture_output=True, text=True).stdout)
    tiles = []
    for i in (0, n // 2, n - 1):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", f"select=eq(n\\,{i})," + to_rgb(TW, TH, "limited", "rgb24"),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        t = np.frombuffer(raw, np.uint8).reshape(TH, TW, 3)[..., ::-1].copy()
        cv2.rectangle(t, (0, 0), (TW, 18), (0, 0, 0), -1)
        cv2.putText(t, f"{os.path.basename(f)[:3]} f{i}/{n}", (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        tiles.append(t)
    cols.append(np.vstack(tiles))
sheet = np.hstack([np.pad(c, ((0, 0), (0, 4), (0, 0)), constant_values=255) for c in cols])
cv2.imwrite(os.path.join(ROOT, "assets", "shots_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("shots sheet", sheet.shape)
