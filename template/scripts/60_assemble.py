"""Phase 9: assemble the rough cut from the rendered shots (hard cuts, EDL order) + ambience mix.
No grain (grain is a final-export step). Preview encode: H.264 High, CRF 18, 1080x1920, CFR 30,
yuv420p, BT.709 tagged, AAC 48 kHz 320k, faststart.  Output: previews/rough_cut_v<N>.mp4"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_edl import load_edl

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ver = args[0] if args else "1"
MUTE = "--mute" in sys.argv     # v2+: user asked for no sound at all -> no audio stream
shots = [os.path.join(ROOT, "work", "shots", f"{s['id']}.mov") for s in load_edl()]
lst = os.path.join(ROOT, "work", "concat.txt")
open(lst, "w").write("".join(f"file '{p}'\n" for p in shots))
master = os.path.join(ROOT, "work", "timeline_prores.mov")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", master], check=True)
out = os.path.join(ROOT, "previews", f"rough_cut_v{ver}.mp4")
audio_in = [] if MUTE else ["-i", os.path.join(ROOT, "work", "audio", "mix.wav")]
maps = ["-map", "0:v"] + ([] if MUTE else ["-map", "1:a"])
aenc = ["-an"] if MUTE else ["-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest"]
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, *audio_in, *maps,
                "-vf", "scale=in_range=tv:out_range=tv,format=yuv420p,limiter=min=16:max=235:planes=1",   # legal luma: codec noise dipped dark pixels below 16
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", "30",
                "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                *aenc, "-movflags", "+faststart", out], check=True)
print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate,pix_fmt,color_range,color_primaries,sample_rate",
                      "-of", "compact", out], capture_output=True, text=True).stdout)
