"""Phase 10.2: finishing trims (applied AFTER the look, per shot), only where shot-to-shot matching
(assets/shot_match.csv) shows a measured outlier.
  S02: sunlit sand chroma 7.99 vs dusty road/bridge deck in S10 4.06 at the same hue (~70-75 deg)
       -> hue-weighted chroma reduction on yellow-orange (OKLab hue 70 +- 35 deg) to ~5.5.
Output: assets/looks/finish_S02_sand.cube, assets/finishing_log.csv"""
import csv, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_color import rgb_to_oklab, oklab_to_rgb, lch, from_lch, hue_weight, smoothstep, gamut_map, write_cube

LK = os.path.join(ROOT, "assets", "looks")
SAND_FACTOR = 5.5 / 7.99


def sand_trim(rgb):
    L, C, h = lch(rgb_to_oklab(rgb))
    w = hue_weight(h, 70.0, 35.0) * smoothstep(0.015, 0.04, C)     # only coloured yellow-orange pixels
    C2 = C * (1 - (1 - SAND_FACTOR) * w)
    return np.clip(oklab_to_rgb(from_lch(L, gamut_map(L, C2, h), h)), 0, 1)


write_cube(os.path.join(LK, "finish_S02_sand.cube"), sand_trim, title="S02 sand chroma trim")
with open(os.path.join(ROOT, "assets", "finishing_log.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["shot", "issue", "metric_before", "reference", "action", "file"])
    w.writerow(["S02", "orange sand after dehaze+base+look", "ground chroma 7.99 (OKLab x100), hue 69.7",
                "S10 dusty road 4.06 at hue 75.2", f"chroma x{SAND_FACTOR:.3f} on hue 70+-35 (C-weighted)",
                "assets/looks/finish_S02_sand.cube"])
print("sand factor", round(SAND_FACTOR, 3))
