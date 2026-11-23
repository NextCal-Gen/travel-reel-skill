#!/usr/bin/env bash
# Phase 1.1: dump ffprobe / mediainfo / exiftool metadata for every clip in raw/.
# Read-only on raw/. Output: assets/metadata/<file>.{ffprobe,mediainfo,exiftool}.json
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/metadata
shopt -s nullglob nocaseglob
for f in raw/*.{mp4,mov,insv,lrv,mkv}; do
  b=$(basename "$f")
  ffprobe -v error -print_format json -show_format -show_streams \
          -show_entries stream_side_data -show_frames -read_intervals "%+#1" \
          "$f" > "assets/metadata/$b.ffprobe.json"
  mediainfo --Output=JSON "$f" > "assets/metadata/$b.mediainfo.json"
  exiftool -json -G1 -a -u -ee3 -api LargeFileSupport=1 "$f" > "assets/metadata/$b.exiftool.json" 2>/dev/null || true
  echo "ok $b"
done
