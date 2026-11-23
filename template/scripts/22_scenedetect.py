"""Phase 5.3: PySceneDetect (ContentDetector) on the proxies -> assets/scenes.csv.
For 360 clips the detector sees the whole equirect frame (any cut or big change anywhere)."""
import csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, proxy_path
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

rows = []
for clip, row in inventory().items():
    v = open_video(proxy_path(clip))
    sm = SceneManager(); sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=15))
    sm.auto_downscale = True
    sm.detect_scenes(v)
    scenes = sm.get_scene_list()
    if not scenes:
        rows.append(dict(clip=clip, scene=1, start=0.0, end=float(row["duration_s"]))); continue
    for i, (a, b) in enumerate(scenes, 1):
        rows.append(dict(clip=clip, scene=i, start=round(a.get_seconds(), 2), end=round(b.get_seconds(), 2)))
with open(os.path.join(ROOT, "assets", "scenes.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(r)
