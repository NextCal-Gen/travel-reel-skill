"""Phase 12: final delivery encode from the 10-bit graded timeline (built from ORIGINALS, never from
previews). Spec (travel-reel skill, Phase 12) with user overrides noted:
  H.264 High, libx264 -preset slow -crf 16 -maxrate 25M -bufsize 50M, yuv420p, 1080x1920, CFR 30,
  BT.709 tagged, +faststart; fine grain before encode (temporal uniform, std 0.67 code values,
  calibrated), 10->8-bit with error-diffusion dither (banding); legal luma floor (codec undershoot).
  AUDIO: none by default (user preference); --audio only when SFX were chosen at kickoff.
  --audio <wav>: mux an audio track (e.g. work/audio/sfx.wav from 93_text_sfx.py, only if SFX were chosen).
  --phone: also write <out>_phone.mp4 (720x1280, CRF 26, ~5 MB) for reviewing on a phone; never post it.
Usage: 80_export.py <out.mp4> [--floor 16] [--no-grain] [--master path] [--audio wav] [--phone]
  master: work/timeline_motion.mov (motion graphics) > work/timeline_text.mov (captions) > timeline_prores.mov"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

out = sys.argv[1]
floor = int(sys.argv[sys.argv.index("--floor") + 1]) if "--floor" in sys.argv else 16
grain = "" if "--no-grain" in sys.argv else "noise=c0s=2:c0f=t+u,"
if "--master" in sys.argv:
    master = sys.argv[sys.argv.index("--master") + 1]
else:                                                                 # top-most finished layer, unless told otherwise
    master = next(os.path.join(ROOT, "work", f) for f in ("timeline_motion.mov", "timeline_text.mov", "timeline_prores.mov")
                  if os.path.exists(os.path.join(ROOT, "work", f)) or f == "timeline_prores.mov")
print("master:", os.path.relpath(master, ROOT))
vf = (f"format=yuv420p10le,{grain}scale=sws_dither=ed,format=yuv420p,"
      f"limiter=min={floor}:max=235:planes=1")
audio = sys.argv[sys.argv.index("--audio") + 1] if "--audio" in sys.argv else None
a_in = ["-i", audio] if audio else []
a_out = (["-map", "1:a", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest"] if audio else ["-an"])
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, *a_in, "-map", "0:v", "-vf", vf,
                "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "25M", "-bufsize", "50M",
                "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30", "-fps_mode", "cfr",
                "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                *a_out, "-map_metadata", "-1", "-map_chapters", "-1",   # no GPS / device metadata in what gets posted
                "-movflags", "+faststart", out], check=True)
print(out)
if "--phone" in sys.argv:                                             # review copy, made from the final file
    ph = os.path.splitext(out)[0] + "_phone.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf", "scale=720:1280:flags=lanczos", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                    "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    *(["-c:a", "aac", "-b:a", "128k"] if audio else ["-an"]),
                    "-map_metadata", "-1", "-movflags", "+faststart", ph], check=True)
    print(ph, f"{os.path.getsize(ph) / 1e6:.1f} MB")
