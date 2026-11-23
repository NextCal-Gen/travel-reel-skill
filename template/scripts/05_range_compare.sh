#!/usr/bin/env bash
# Phase 1.3b: visual check of range interpretation. For a clip, render the same frame decoded
# as limited (tv, as tagged) vs full (pc, as the measured data suggests), side by side.
# Usage: scripts/05_range_compare.sh <clip> <time_s>   -> assets/range_compare/<clip>_<t>.jpg
set -euo pipefail
cd "$(dirname "$0")/.."
clip="$1"; t="$2"; b=$(basename "$clip" .mp4)
mkdir -p assets/range_compare
ffmpeg -v error -y -ss "$t" -i "raw/$clip" -frames:v 1 -filter_complex "
 [0:v]split[a][b];
 [a]scale=1200:-2:in_range=tv:out_range=pc:in_color_matrix=bt709,format=rgb24[tv];
 [b]scale=1200:-2:in_range=pc:out_range=pc:in_color_matrix=bt709,format=rgb24[pc];
 [tv][pc]vstack" -q:v 3 "assets/range_compare/${b}_${t}.jpg"
echo "assets/range_compare/${b}_${t}.jpg  (top = decoded as LIMITED/tv, bottom = decoded as FULL/pc)"
