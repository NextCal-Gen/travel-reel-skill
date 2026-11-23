#!/usr/bin/env bash
# Phase 5.1: 10-bit analysis proxies with correct colour/geometry (NOT used for final renders).
#  - 360 clips: equirect 2880x1440, native fps; range fixed per inventory (full) and converted
#    to standard limited-range BT.709 10-bit, correctly tagged.
#  - Samsung: rotation applied (autorotate), 1080x1920, limited range as tagged.
# Encoder: hevc_videotoolbox main10 (fast, small). Output: work/proxies/<clip>.mov
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
mkdir -p work/proxies
python - <<'EOF'
import csv, subprocess, os, sys
sys.path.insert(0, "scripts")
from lib_reel import inventory, is360, input_transform, range_of
for clip, row in inventory().items():
    out = f"work/proxies/{os.path.splitext(clip)[0]}.mov"
    if os.path.exists(out): print("exists", out); continue
    geo = "2880:1440" if is360(row) else "1080:1920"
    vf = (input_transform(row) +
          f",zscale=w={geo.split(':')[0]}:h={geo.split(':')[1]}:filter=lanczos:rangein={range_of(row)}:range=limited:"
          "matrixin=709:matrix=709:primariesin=709:primaries=709:transferin=709:transfer=709,format=p010le")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"raw/{clip}", "-vf", vf,
                    "-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", "70", "-tag:v", "hvc1",
                    "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-c:a", "copy", out], check=True)
    print("ok", out)
EOF
du -sh work/proxies
