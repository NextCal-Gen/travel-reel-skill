"""Phase 1.2: extract N evenly spaced frames per clip and tile them into a labelled contact sheet.
Frames are decoded with ffmpeg (rotation metadata honoured, no colour transform applied:
this is the raw look of the source, which is what classification needs).
Output: assets/contact_sheets/<clip>.jpg   (temp frames in work/frames/, deleted after)."""
import glob, os, subprocess, sys, json, shutil
import cv2, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(os.environ.get("N_FRAMES", 9))
OUT = os.path.join(ROOT, "assets", "contact_sheets")
TMP = os.path.join(ROOT, "work", "frames")
os.makedirs(OUT, exist_ok=True)


def duration(path):
    j = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]))
    return float(j["format"]["duration"])


def grab(path, t, dst, width):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path,
                    "-frames:v", "1", "-vf", f"scale={width}:-2:flags=area",
                    "-q:v", "3", dst], check=True)


clips = sorted(glob.glob(os.path.join(ROOT, "raw", "*.mp4")) + glob.glob(os.path.join(ROOT, "raw", "*.MP4"))
               + glob.glob(os.path.join(ROOT, "raw", "*.mov")) + glob.glob(os.path.join(ROOT, "raw", "*.MOV")))
only = sys.argv[1:]
for path in clips:
    name = os.path.basename(path)
    if only and name not in only:
        continue
    d = duration(path)
    times = [d * (i + 0.5) / N for i in range(N)]
    tdir = os.path.join(TMP, name)
    os.makedirs(tdir, exist_ok=True)
    tiles = []
    for i, t in enumerate(times):
        f = os.path.join(tdir, f"{i:02d}.jpg")
        grab(path, t, f, 960)
        img = cv2.imread(f)
        label = f"{t:5.2f}s"
        cv2.rectangle(img, (0, 0), (150, 40), (0, 0, 0), -1)
        cv2.putText(img, label, (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        tiles.append(img)
    h = max(t.shape[0] for t in tiles); w = max(t.shape[1] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, w - t.shape[1], cv2.BORDER_CONSTANT) for t in tiles]
    cols = 3
    rows = [np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(N // cols)]
    sheet = np.vstack(rows)
    # Keep sheet readable but not huge
    scale = min(1.0, 2400 / sheet.shape[1])
    sheet = cv2.resize(sheet, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, os.path.splitext(name)[0] + ".jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    shutil.rmtree(tdir)
    print("sheet", name, f"{d:.1f}s")
