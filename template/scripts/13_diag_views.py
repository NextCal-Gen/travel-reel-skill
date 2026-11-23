"""Phase 3c: render specific 9:16 analysis views (working-space decode) for visual
confirmation of diagnostic triggers. Usage:
  13_diag_views.py <clip> <time_s> <yaw|flat> [pitch] [h_fov]   -> assets/diag_views/<clip>_<t>_<yaw>.jpg"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, is360, v360_view, grab_rgb, save_jpg

clip, t, yaw = sys.argv[1], float(sys.argv[2]), sys.argv[3]
pitch = float(sys.argv[4]) if len(sys.argv) > 4 else 0
hfov = float(sys.argv[5]) if len(sys.argv) > 5 else 70
row = inventory()[clip]
if is360(row) and yaw != "flat":
    rgb = grab_rgb(clip, t, v360_view(float(yaw), pitch, 0, hfov, 540, 960), 540, 960, row=row)
else:
    rgb = grab_rgb(clip, t, "", 540, 960, row=row)
out = os.path.join(ROOT, "assets", "diag_views", f"{os.path.splitext(clip)[0]}_{t:.1f}_{yaw}.jpg")
save_jpg(out, rgb)
print(out)
