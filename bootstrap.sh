#!/usr/bin/env bash
# travel-reel toolkit bootstrap: one shared toolchain for every trip folder.
#
#   bootstrap.sh --check                 verify system tools + shared toolkit (exit 0 = ready)
#   bootstrap.sh --install-system        install the missing Homebrew packages (ffmpeg tap build, mediainfo,
#                                        exiftool, python@3.12, molten-vk); ~30-40 min. Ask the user first.
#   bootstrap.sh --use-defaults <name>   copy defaults/<name>.defaults.md to ~/.claude/travel-reel.defaults.md
#   bootstrap.sh --create [--with-df] [--with-motion]   build whatever is missing in the toolkit (downloads from
#                                        PyPI / official GitHub releases / opencv_zoo; tell the user first)
#   bootstrap.sh --init-reel <proj> <id> create reels/<id>/ sharing the project's raw/, metadata, inventory, proxies
#   bootstrap.sh --init-project <dir>    create trip folder layout + scripts/env.sh + CLAUDE.md template
#                                        (+ personal standing defaults from ~/.claude/travel-reel.defaults.md)
#
# Toolkit location: $TRAVEL_REEL_TOOLKIT (default ~/travel-reel-toolkit).
# System packages (Homebrew) are installed only by --install-system, which the skill runs after the user
# says yes once. Homebrew itself needs the user's password and is never installed here.
set -u
TK="${TRAVEL_REEL_TOOLKIT:-$HOME/travel-reel-toolkit}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY312="/opt/homebrew/opt/python@3.12/bin/python3.12"
RIFE_URL="https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-macos.zip"
YUNET_URL="https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_SHA="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
YOLO_URL="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
YOLO_SIZE=5613764
# motion graphics (optional): pinned, published > 2 weeks before pinning; never `npx hyperframes@latest`
HF_VERSION="0.8.34"; GSAP_VERSION="3.14.2"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
# keep tool caches/settings inside the toolkit (the import tests would otherwise write to ~/.matplotlib etc.)
export MPLCONFIGDIR="$TK/cache/matplotlib" YOLO_CONFIG_DIR="$TK/cache/ultralytics" TORCH_HOME="$TK/cache/torch" HF_HOME="$TK/cache/huggingface"

ok=0; fail=0
pass() { printf "  PASS  %s\n" "$1"; ok=$((ok+1)); }
miss() { printf "  MISS  %s\n        -> %s\n" "$1" "$2"; fail=$((fail+1)); }

check_system() {
  echo "System tools"
  # the ffmpeg first on PATH is the one every script uses: a non-Homebrew copy (static download, conda, MacPorts)
  # earlier in PATH hides the tap build, and --install-system would then "succeed" while the checks still fail
  local ffp; ffp=$(command -v ffmpeg 2>/dev/null || true)
  if [ -n "$ffp" ] && [ -x /opt/homebrew/bin/ffmpeg ] && [ "$ffp" != /opt/homebrew/bin/ffmpeg ]; then
    printf "  WARN  ffmpeg on PATH is %s, not Homebrew's /opt/homebrew/bin/ffmpeg: remove it or put /opt/homebrew/bin first in PATH\n" "$ffp"
  fi
  if command -v ffmpeg >/dev/null; then
    F=$(ffmpeg -hide_banner -filters 2>/dev/null)
    for f in zscale libplacebo libvmaf v360 lut3d; do
      echo "$F" | grep -qE "^ [.A-Z|]+ $f " && pass "ffmpeg filter $f" \
        || miss "ffmpeg filter $f" "brew tap homebrew-ffmpeg/ffmpeg && brew trust --formula homebrew-ffmpeg/ffmpeg/ffmpeg && brew uninstall ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg --with-libplacebo --with-libvmaf"
    done
    ffmpeg -v error -init_hw_device vulkan -f lavfi -i testsrc2=d=0.1 -vf format=yuv420p,hwupload,libplacebo,hwdownload,format=yuv420p -f null - 2>/dev/null \
      && pass "libplacebo on GPU (Vulkan/MoltenVK)" || miss "libplacebo on GPU" "brew install molten-vk  (and DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib, set by env.sh)"
  else miss "ffmpeg" "see filter line above (homebrew-ffmpeg tap build)"; fi
  command -v ffprobe >/dev/null && pass "ffprobe" || miss "ffprobe" "comes with ffmpeg"
  command -v mediainfo >/dev/null && pass "mediainfo $(mediainfo --Version 2>/dev/null | tail -1 | sed 's/.*- //')" || miss "mediainfo" "brew install media-info"
  command -v exiftool >/dev/null && pass "exiftool $(exiftool -ver)" || miss "exiftool" "brew install exiftool"
  [ -x "$PY312" ] && pass "python 3.12 ($("$PY312" --version 2>&1))" || miss "python 3.12" "brew install python@3.12"
  for font in "Avenir Next.ttc" "Supplemental/Futura.ttc" "Supplemental/Didot.ttc" "Optima.ttc" "Apple Color Emoji.ttc"; do
    [ -f "/System/Library/Fonts/$font" ] && pass "font $(basename "$font" .ttc) (captions/map labels)" \
      || miss "font $(basename "$font" .ttc)" "macOS system font missing at /System/Library/Fonts/$font; edit lib_text.py F/EMOJI_FONT to an installed font"
  done
}

check_toolkit() {
  echo "Shared toolkit: $TK"
  [ -d "$TK" ] || { miss "toolkit folder" "bootstrap.sh --create"; return; }
  if [ -x "$TK/venv/bin/python" ] && "$TK/venv/bin/python" -c "import numpy, cv2, colour, PyOpenColorIO, librosa, scenedetect, opentimelineio, PIL, ultralytics, scipy" 2>/dev/null; then
    pass "main venv imports ($("$TK/venv/bin/python" --version 2>&1))"
    "$TK/venv/bin/python" -c "import torch,sys; sys.exit(0 if torch.backends.mps.is_available() else 1)" 2>/dev/null && pass "torch MPS (GPU)" || miss "torch MPS" "optional; CPU fallback"
  else miss "main venv" "bootstrap.sh --create"; fi
  if [ -x "$TK/venv-df/bin/python" ]; then
    "$TK/venv-df/bin/python" -c "import df" 2>/dev/null && pass "DeepFilterNet venv (optional, audio only)" || miss "DeepFilterNet venv" "bootstrap.sh --create --with-df (optional)"
  else printf "  SKIP  DeepFilterNet venv (optional; default reels have no audio)\n"; fi
  if [ -x "$TK/rife/rife-ncnn-vulkan" ] && [ -d "$TK/rife/rife-v4.6" ]; then
    d=$(mktemp -d); ffmpeg -v error -f lavfi -i testsrc2=s=320x180:d=1 -vf "select=eq(n\,0)+eq(n\,10)" -fps_mode passthrough "$d/f%d.png" 2>/dev/null
    (cd "$TK/rife" && ./rife-ncnn-vulkan -0 "$d/f1.png" -1 "$d/f2.png" -o "$d/mid.png" -m rife-v4.6 >/dev/null 2>&1) && [ -f "$d/mid.png" ] \
      && pass "RIFE interpolation on GPU" || miss "RIFE run" "bootstrap.sh --create (re-download)"; rm -rf "$d"
  else miss "RIFE" "bootstrap.sh --create"; fi
  if [ -f "$TK/models/face_detection_yunet_2023mar.onnx" ] && [ "$(shasum -a 256 "$TK/models/face_detection_yunet_2023mar.onnx" | cut -d' ' -f1)" = "$YUNET_SHA" ]; then pass "YuNet face model (sha256 ok; optional)"; else miss "YuNet face model (optional)" "bootstrap.sh --create"; fi
  if [ -f "$TK/models/yolo11n.pt" ] && [ "$(stat -f %z "$TK/models/yolo11n.pt")" = "$YOLO_SIZE" ]; then pass "YOLO11n person model (optional)"; else miss "YOLO11n person model (optional)" "bootstrap.sh --create"; fi
  check_motion
}

node22() {
  # path of a Node >= 22 binary: PATH first, then nvm installs (newest first), then Homebrew. nvm users often
  # have an older default node first on PATH, and HyperFrames' launcher uses whatever `node` PATH gives it.
  local c v
  for c in "$(command -v node 2>/dev/null)" $(ls -d "$HOME"/.nvm/versions/node/v*/bin/node 2>/dev/null | sort -V -r) \
           /opt/homebrew/opt/node/bin/node /opt/homebrew/bin/node /usr/local/bin/node; do
    [ -x "$c" ] || continue
    v=$("$c" -p 'process.versions.node.split(".")[0]' 2>/dev/null) || continue
    [ "${v:-0}" -ge 22 ] 2>/dev/null && { echo "$c"; return 0; }
  done
  return 1
}
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
motion_env() {
  # PATH with Node 22+ first, and an installed Google Chrome as the render browser unless MOTION_BROWSER is set
  local n; n=$(node22) && export PATH="$(dirname "$n"):$PATH"
  [ -z "${MOTION_BROWSER:-}" ] && [ -x "$CHROME_APP" ] && export MOTION_BROWSER="$CHROME_APP"
  return 0
}

check_motion() {
  local HFB="$TK/motion/node_modules/.bin/hyperframes"
  if ! [ -x "$HFB" ]; then printf "  SKIP  motion graphics (optional; bootstrap.sh --install-system --with-motion, then --create --with-motion)\n"; return; fi
  motion_env
  node22 >/dev/null && pass "node $("$(node22)" --version) for motion graphics" || miss "Node 22+ (motion graphics)" "bootstrap.sh --install-system --with-motion"
  local v; v=$("$HFB" --version 2>/dev/null)
  [ "$v" = "$HF_VERSION" ] && pass "hyperframes $v (pinned)" || miss "hyperframes $HF_VERSION (found: ${v:-none})" "bootstrap.sh --create --with-motion"
  [ -f "$TK/motion/node_modules/gsap/dist/gsap.min.js" ] && pass "gsap (vendored into each render)" || miss "gsap" "bootstrap.sh --create --with-motion"
  # one real 1-second transparent render: proves Node, Chrome, ffmpeg and alpha output end to end
  local d; d=$(mktemp -d); mkdir -p "$d/assets/vendor"; cp "$TK/motion/node_modules/gsap/dist/gsap.min.js" "$d/assets/vendor/" 2>/dev/null
  cat > "$d/index.html" <<'HTML'
<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=320, height=240" />
<script src="assets/vendor/gsap.min.js"></script>
<style>html,body{margin:0;width:320px;height:240px;background:transparent}#b{position:absolute;left:40px;top:80px;width:80px;height:80px;background:#e33}</style></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="1" data-width="320" data-height="240"><div id="b"></div></div>
<script>window.__timelines = window.__timelines || {}; var tl = gsap.timeline({ paused: true }); tl.to('#b', { x: 160, duration: 1 }); window.__timelines["main"] = tl;</script>
</body></html>
HTML
  local envs=(HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1)
  [ -n "${MOTION_BROWSER:-}" ] && envs+=("HYPERFRAMES_BROWSER_PATH=$MOTION_BROWSER")
  if env "${envs[@]}" "$HFB" render "$d" --format mov -o "$d/t.mov" --quiet >/dev/null 2>&1 \
     && ffprobe -v error -show_entries stream=pix_fmt -of csv=p=0 "$d/t.mov" 2>/dev/null | grep -q "yuva"; then
    pass "motion test render (transparent ProRes 4444)"
  else miss "motion test render" "bootstrap.sh --create --with-motion (installs Chrome via 'hyperframes browser ensure')"; fi
  rm -rf "$d"
}

create() {
  mkdir -p "$TK/models" "$TK/cache/matplotlib" "$TK/cache/ultralytics" "$TK/cache/torch" "$TK/cache/huggingface"
  [ -x "$PY312" ] || { echo "python 3.12 missing: brew install python@3.12 (ask the user), then re-run"; exit 1; }
  if ! [ -x "$TK/venv/bin/python" ]; then
    echo "Creating main venv from requirements-main.lock"
    "$PY312" -m venv "$TK/venv" && "$TK/venv/bin/python" -m pip install -q --upgrade pip
    LOCK="$TK/requirements-main.lock"; [ -f "$LOCK" ] || LOCK="$SKILL_DIR/requirements-main.lock"
    "$TK/venv/bin/python" -m pip install -q -r "$LOCK" || { echo "pip install failed"; exit 1; }
  fi
  if [ "${WITH_DF:-0}" = 1 ] && ! [ -x "$TK/venv-df/bin/python" ]; then
    echo "Creating DeepFilterNet venv (needs Rust: brew install rust)"
    "$PY312" -m venv "$TK/venv-df" && "$TK/venv-df/bin/python" -m pip install -q --upgrade pip
    LOCK="$TK/requirements-df.lock"; [ -f "$LOCK" ] || LOCK="$SKILL_DIR/requirements-df.lock"
    "$TK/venv-df/bin/python" -m pip install -q -r "$LOCK"
  fi
  if ! [ -x "$TK/rife/rife-ncnn-vulkan" ]; then
    echo "Downloading RIFE (436 MB, official GitHub release)"
    d=$(mktemp -d); curl -fsSL -o "$d/rife.zip" "$RIFE_URL" && unzip -q "$d/rife.zip" -d "$d/x" \
      && mv "$d/x/rife-ncnn-vulkan-20221029-macos" "$TK/rife" && chmod +x "$TK/rife/rife-ncnn-vulkan"; rm -rf "$d"
  fi
  if [ -f "$TK/models/face_detection_yunet_2023mar.onnx" ] && [ "$(shasum -a 256 "$TK/models/face_detection_yunet_2023mar.onnx" | cut -d' ' -f1)" != "$YUNET_SHA" ]; then
    echo "YuNet sha256 mismatch: re-downloading"; rm -f "$TK/models/face_detection_yunet_2023mar.onnx"
  fi
  if ! [ -f "$TK/models/face_detection_yunet_2023mar.onnx" ]; then
    curl -fsSL -o "$TK/models/face_detection_yunet_2023mar.onnx" "$YUNET_URL" || rm -f "$TK/models/face_detection_yunet_2023mar.onnx"
    [ ! -f "$TK/models/face_detection_yunet_2023mar.onnx" ] || [ "$(shasum -a 256 "$TK/models/face_detection_yunet_2023mar.onnx" | cut -d' ' -f1)" = "$YUNET_SHA" ] || { echo "YuNet sha256 mismatch: removed"; rm -f "$TK/models/face_detection_yunet_2023mar.onnx"; }
  fi
  # a partial or failed download (e.g. a saved 404 page) must not block future --create runs
  if [ -f "$TK/models/yolo11n.pt" ] && [ "$(stat -f %z "$TK/models/yolo11n.pt")" != "$YOLO_SIZE" ]; then
    echo "YOLO11n size mismatch: re-downloading"; rm -f "$TK/models/yolo11n.pt"
  fi
  if ! [ -f "$TK/models/yolo11n.pt" ]; then
    curl -fsSL -o "$TK/models/yolo11n.pt" "$YOLO_URL" || rm -f "$TK/models/yolo11n.pt"
    [ ! -f "$TK/models/yolo11n.pt" ] || [ "$(stat -f %z "$TK/models/yolo11n.pt")" = "$YOLO_SIZE" ] \
      || { echo "YOLO11n size mismatch: removed"; rm -f "$TK/models/yolo11n.pt"; }
  fi
  if [ "${WITH_MOTION:-0}" = 1 ]; then create_motion; fi
  echo "create done"
}

create_motion() {
  # HyperFrames (HTML/GSAP -> video) for motion-graphic overlays. --ignore-scripts skips onnxruntime's
  # postinstall (only used by background removal, which this skill doesn't use).
  motion_env
  node22 >/dev/null || { echo "motion: Node 22+ missing -> bootstrap.sh --install-system --with-motion"; return; }
  mkdir -p "$TK/motion"
  [ -f "$TK/motion/package.json" ] || printf '{ "name": "travel-reel-motion-toolkit", "private": true }\n' > "$TK/motion/package.json"
  if ! [ -x "$TK/motion/node_modules/.bin/hyperframes" ] || [ "$("$TK/motion/node_modules/.bin/hyperframes" --version 2>/dev/null)" != "$HF_VERSION" ] \
     || ! [ -f "$TK/motion/node_modules/gsap/dist/gsap.min.js" ]; then
    (cd "$TK/motion" && npm install --no-audit --no-fund --ignore-scripts --save-exact "hyperframes@$HF_VERSION" "gsap@$GSAP_VERSION") || { echo "motion: npm install failed"; return; }
  fi
  if [ -n "${MOTION_BROWSER:-}" ]; then echo "motion: rendering with $MOTION_BROWSER (no browser download)"
  else                                                       # no Google Chrome installed: HyperFrames fetches its own
    HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 "$TK/motion/node_modules/.bin/hyperframes" browser ensure \
      || echo "motion: Chrome for rendering not installed (re-run, or set MOTION_BROWSER to a Chrome binary)"
  fi
}

init_project() {
  P="$1"; mkdir -p "$P"/{raw,references/look,luts,assets/map,scripts,work,previews/finishing_comparison,outputs}
  if ! [ -f "$P/scripts/env.sh" ]; then
    cat > "$P/scripts/env.sh" <<'EOF'
# Source before running any processing script:  source scripts/env.sh
# Uses the SHARED travel-reel toolkit (venv, RIFE, models, caches); nothing is installed per project.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")/.." && pwd)"; export PROJECT_ROOT
export TRAVEL_REEL_TOOLKIT="${TRAVEL_REEL_TOOLKIT:-$HOME/travel-reel-toolkit}"
TK="$TRAVEL_REEL_TOOLKIT"
if [ ! -x "$TK/venv/bin/python" ]; then
  echo "travel-reel toolkit not found at $TK -> run: ~/.claude/skills/travel-reel/bootstrap.sh --check / --create" >&2
  return 1 2>/dev/null || exit 1
fi
# libplacebo / RIFE load libvulkan at runtime; macOS doesn't search /opt/homebrew/lib by default.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
export TOOL_CACHE="$TK/cache"
export MPLCONFIGDIR="$TOOL_CACHE/matplotlib" YOLO_CONFIG_DIR="$TOOL_CACHE/ultralytics"
export TORCH_HOME="$TOOL_CACHE/torch" HF_HOME="$TOOL_CACHE/huggingface" CARGO_HOME="$TOOL_CACHE/cargo"
export TRAVEL_REEL_MODELS="$TK/models"
export RIFE_BIN="$TK/rife/rife-ncnn-vulkan" RIFE_MODEL_DIR="$TK/rife"
export DF_PY="$TK/venv-df/bin/python" DF_MODEL_DIR="$TK/deepfilternet/DeepFilterNet3"
source "$TK/venv/bin/activate"
EOF
    echo "wrote $P/scripts/env.sh"
  fi
  # CLAUDE.md = public template + the user's PERSONAL defaults file (kept outside this public repo):
  #   "## Config overrides" section: "- Key: value" lines replace the template line with the same key
  #                                  (e.g. "- Gate 1 auto-continue: yes", "- Opener: ...")
  #   everything else: replaces the block between the standing-defaults markers
  DEF="${TRAVEL_REEL_DEFAULTS:-$HOME/.claude/travel-reel.defaults.md}"
  if [ -z "${SKIP_CLAUDE_MD:-}" ] && [ ! -f "$P/CLAUDE.md" ]; then
    if [ -f "$DEF" ]; then
      awk -v def="$DEF" '
        BEGIN { sec = "body"
                while ((getline l < def) > 0) {
                  if (l ~ /^## Config overrides/) { sec = "cfg"; continue }
                  if (l ~ /^## /) sec = "body"
                  if (sec == "cfg") { if (l ~ /^- [^:]+:/) { k = l; sub(/:.*/, "", k); ov[k] = l } }
                  else body[++nb] = l } }
        /<!-- standing-defaults:start -->/ { print; for (i = 1; i <= nb; i++) print body[i]; skip = 1; next }
        /<!-- standing-defaults:end -->/ { skip = 0 }
        skip { next }
        cont && /^  / { next }                                   # drop the replaced line'\''s continuation lines
        { cont = 0 }
        /^- [^:]+:/ { k = $0; sub(/:.*/, "", k); if (k in ov) { print ov[k]; cont = 1; next } }
        { print }' "$SKILL_DIR/CLAUDE.template.md" > "$P/CLAUDE.md"
      echo "wrote $P/CLAUDE.md (fill in the trip name; defaults + config overrides from $DEF)"
    else
      cp "$SKILL_DIR/CLAUDE.template.md" "$P/CLAUDE.md" && echo "wrote $P/CLAUDE.md (fill in the trip name; no personal defaults file at $DEF)"
    fi
  fi
  # pipeline template (tested scripts) - only into a scripts/ folder that has no scripts yet
  if ! ls "$P"/scripts/*.py >/dev/null 2>&1; then
    cp "$SKILL_DIR"/template/scripts/* "$P/scripts/" && cp "$SKILL_DIR/template/README.md" "$P/scripts/README.md" \
      && echo "copied pipeline template ($(ls "$SKILL_DIR"/template/scripts | wc -l | tr -d ' ') scripts) + scripts/README.md"
  else echo "scripts/ already has scripts: template not copied"; fi
  # standing look + camera-match LUTs - never overwrite
  mkdir -p "$P/assets/looks"
  for f in "$SKILL_DIR"/template/looks/*; do [ -e "$P/assets/looks/$(basename "$f")" ] || cp "$f" "$P/assets/looks/"; done
  echo "standing look in assets/looks/ (look2_warm_cinematic.cube + base camera matches)"
  # unattended-run permission allowlist + editable visit types (multi-reel planning) - never overwrite
  [ -n "${SKIP_CLAUDE_MD:-}" ] || mkdir -p "$P/.claude"
  [ -n "${SKIP_CLAUDE_MD:-}" ] || [ -e "$P/.claude/settings.json" ] || { cp "$SKILL_DIR/template/settings.json" "$P/.claude/settings.json" && echo "wrote $P/.claude/settings.json (permission allowlist)"; }
  [ -e "$P/assets/visit_types.json" ] || cp "$SKILL_DIR/visit_types.json" "$P/assets/visit_types.json"
  echo "project ready: $P"
}

init_reel() {
  # reels/<id>/ = a normal project that shares the parent's raw clips, metadata, inventory and proxies
  local PROJ REEL
  PROJ="$(cd "$1" && pwd)"; REEL="$PROJ/reels/$2"
  [ -d "$PROJ/raw" ] || { echo "no raw/ in $PROJ"; exit 2; }
  mkdir -p "$PROJ/assets/metadata" "$PROJ/work/proxies"
  SKIP_CLAUDE_MD=1 init_project "$REEL" >/dev/null       # init_project sets the global P
  rmdir "$REEL/raw" 2>/dev/null; [ -e "$REEL/raw" ] || ln -s ../../raw "$REEL/raw"
  mkdir -p "$REEL/work"
  [ -e "$REEL/assets/metadata" ] || ln -s ../../../assets/metadata "$REEL/assets/metadata"
  [ -e "$REEL/assets/source_inventory.csv" ] || ln -s ../../../assets/source_inventory.csv "$REEL/assets/source_inventory.csv"
  [ -e "$REEL/work/proxies" ] || ln -s ../../../work/proxies "$REEL/work/proxies"
  [ -e "$REEL/reel.md" ] || printf '# Reel %s\n- Visits/clips:\n- Target duration:\n- Location mode: hide\n- On-screen text:\n- Extras:\n- Opener:\n' "$2" > "$REEL/reel.md"
  echo "reel ready: $REEL (shares raw/, metadata, inventory and proxies with $PROJ)"
}

install_system() {
  # Installs only what is missing. Homebrew itself needs the user's password: never installed here.
  BREW=$(command -v brew || echo /opt/homebrew/bin/brew)
  [ -x "$BREW" ] || { echo "Homebrew is not installed. The user must run this in Terminal (asks for their password):"
                      echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'; exit 1; }
  local pk=()
  command -v mediainfo >/dev/null || pk+=(media-info)
  command -v exiftool >/dev/null || pk+=(exiftool)
  [ -x "$PY312" ] || pk+=(python@3.12)
  "$BREW" list --formula molten-vk >/dev/null 2>&1 || pk+=(molten-vk)
  if [ "${WITH_MOTION:-0}" = 1 ]; then                       # motion graphics need Node 22+ (any nvm/brew install counts)
    node22 >/dev/null || pk+=(node)
  fi
  if [ ${#pk[@]} -gt 0 ]; then echo "brew install ${pk[*]}"; "$BREW" install "${pk[@]}" || exit 1; fi
  local need_ff=0
  if command -v ffmpeg >/dev/null; then
    F=$(ffmpeg -hide_banner -filters 2>/dev/null)
    for f in zscale libplacebo libvmaf v360 lut3d; do echo "$F" | grep -qE "^ [.A-Z|]+ $f " || need_ff=1; done
  else need_ff=1; fi
  if [ $need_ff = 1 ]; then
    echo "Building ffmpeg from the homebrew-ffmpeg tap with zimg, libplacebo, libvmaf (the long part)"
    "$BREW" tap homebrew-ffmpeg/ffmpeg && "$BREW" trust --formula homebrew-ffmpeg/ffmpeg/ffmpeg || exit 1
    "$BREW" list --formula ffmpeg >/dev/null 2>&1 && ! "$BREW" list --formula homebrew-ffmpeg/ffmpeg/ffmpeg >/dev/null 2>&1 \
      && "$BREW" uninstall --ignore-dependencies ffmpeg
    "$BREW" install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg --with-libplacebo --with-libvmaf || exit 1
  fi
  [ ${#pk[@]} -eq 0 ] && [ $need_ff = 0 ] && echo "system packages: nothing missing"
  echo "install-system done"
}

use_defaults() {
  local SRC="$SKILL_DIR/defaults/$1.defaults.md" DST="${TRAVEL_REEL_DEFAULTS:-$HOME/.claude/travel-reel.defaults.md}"
  [ -f "$SRC" ] || { echo "no $SRC (available: $(ls "$SKILL_DIR/defaults" 2>/dev/null | sed 's/.defaults.md//' | tr '\n' ' '))"; exit 2; }
  if [ -f "$DST" ] && ! cmp -s "$SRC" "$DST"; then cp "$DST" "$DST.bak" && echo "kept the previous file as $DST.bak"; fi
  mkdir -p "$(dirname "$DST")" && cp "$SRC" "$DST" && echo "personal defaults: $DST (from defaults/$1)"
}

case "${1:-}" in
  --check) check_system; check_toolkit; echo "---- $ok pass, $fail missing"; [ "$fail" = 0 ] ;;
  --create) for a in "${@:2}"; do [ "$a" = "--with-df" ] && WITH_DF=1; [ "$a" = "--with-motion" ] && WITH_MOTION=1; done
            create; check_toolkit ;;
  --install-system) [ "${2:-}" = "--with-motion" ] && WITH_MOTION=1; install_system ;;
  --use-defaults) [ -n "${2:-}" ] || { echo "usage: --use-defaults <name>"; exit 2; }; use_defaults "$2" ;;
  --init-project) [ -n "${2:-}" ] || { echo "usage: --init-project <dir>"; exit 2; }; init_project "$2" ;;
  --init-reel) [ -n "${2:-}" ] && [ -n "${3:-}" ] || { echo "usage: --init-reel <project> <reel_id>"; exit 2; }; init_reel "$2" "$3" ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
