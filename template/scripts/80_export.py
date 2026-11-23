"""Phase 12: final delivery encode from the 10-bit graded timeline (built from ORIGINALS, never from
previews). Spec (travel-reel skill, Phase 12) with user overrides noted:
  H.264 High, libx264 -preset slow -crf 16 -maxrate 25M -bufsize 50M, yuv420p, 1080x1920, CFR 30,
  BT.709 tagged, +faststart; fine grain before encode (temporal uniform, std 0.67 code values,
  calibrated), 10->8-bit with error-diffusion dither (banding); legal luma floor (codec undershoot).
  AUDIO: none (user request v2: "mute the whole video, I don't want sound on it").
Usage: 80_export.py <out.mp4> [--floor 16] [--no-grain] [--master path]"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

out = sys.argv[1]
floor = int(sys.argv[sys.argv.index("--floor") + 1]) if "--floor" in sys.argv else 16
grain = "" if "--no-grain" in sys.argv else "noise=c0s=2:c0f=t+u,"
master = (sys.argv[sys.argv.index("--master") + 1] if "--master" in sys.argv
          else os.path.join(ROOT, "work", "timeline_prores.mov"))     # v6: --master work/timeline_text.mov (captions)
vf = (f"format=yuv420p10le,{grain}scale=sws_dither=ed,format=yuv420p,"
      f"limiter=min={floor}:max=235:planes=1")
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, "-map", "0:v", "-vf", vf,
                "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "25M", "-bufsize", "50M",
                "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-fps_mode", "cfr",
                "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-an", "-movflags", "+faststart", out], check=True)
print(out)
