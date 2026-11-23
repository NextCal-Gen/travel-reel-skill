"""Phase 7.2: natural-ambience mix (no music supplied, no voiceover).
Decisions are driven by assets/audio_analysis.csv:
  - WIND (energy < 150 Hz > 50%)       -> 4th-order zero-phase high-pass at 150 Hz
  - SPEECH? (syllabic modulation > .45) -> S05: replaced by same-clip sanctum ambience (5.0-8.6s);
                                           S07: ducked -8 dB under the mix
  - QUIET/silent S04 (timelapse capture) -> covered by S03's own ambience continuing (same place, +1.6s)
  - DeepFilterNet NOT used: it preserves speech and suppresses non-speech, the opposite of an
    ambience bed. Wind rumble is low-frequency and handled by the high-pass.
Every cut: 60 ms equal-power crossfade (handles taken from source). Head fade 0.25 s, tail 1.2 s.
Segments levelled to a common RMS, then loudness-normalised (ffmpeg loudnorm, 2-pass) to
-14 LUFS integrated, -1.5 dBTP in the mix (AAC encode overshoots ~0.1-0.5 dB; delivery limit is -1 dBTP). Timeline = exact frame counts of the rendered shots (30 fps).
Output: work/audio/mix.wav, assets/audio_mix_log.csv"""
import csv, json, os, subprocess, sys
import numpy as np, scipy.signal as sg, soundfile as sf
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_edl import load_edl

SR, FPS, XF = 48000, 30, 0.06
AD = os.path.join(ROOT, "work", "audio")
edl = load_edl()
ana = {r["id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "assets", "audio_analysis.csv")))}


def nframes(sid):
    return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", os.path.join(ROOT, "work", "shots", f"{sid}.mov")],
                              capture_output=True, text=True).stdout)


def read_src(clip, t0, dur):
    t0c = max(0.0, t0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0c:.4f}", "-t", f"{dur + (t0c - t0):.4f}", "-i",
                          os.path.join(ROOT, "raw", clip), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
    pad_front = int(round((t0c - t0) * SR))
    a = np.vstack([np.zeros((pad_front, 2), np.float32), a])
    need = int(round(dur * SR))
    return np.vstack([a, np.zeros((max(0, need - len(a)), 2), np.float32)])[:need]


def hp(a, fc=150):
    sos = sg.butter(4, fc, btype="high", fs=SR, output="sos")
    return sg.sosfiltfilt(sos, a, axis=0).astype(np.float32)


def rms_db(a):
    return 20 * np.log10(np.sqrt((a.astype(np.float64) ** 2).mean()) + 1e-12)


# --- timeline from rendered frame counts ---
starts, t = {}, 0
for s in edl:
    n = nframes(s["id"]); starts[s["id"]] = (t, n); t += n
total = int(round(t / FPS * SR))
mix = np.zeros((total, 2), np.float64)
log = []
TARGET_RMS = -26.0
OFFSET = {"S02": -3.0, "S07": -8.0, "S11": +2.0}
MAX_BOOST = 8.0   # v1 boosted S02 +16.8 dB / S08 +14.5 dB (mostly hiss after HP) -> capped

for s in edl:
    sid = s["id"]; f0, n = starts[sid]
    a0 = f0 / FPS; dur = n / FPS
    src_clip, src_in, note = s["clip"], s["tin"], "own audio"
    if sid == "S04":
        src_clip, src_in, note = edl[2]["clip"], edl[2]["tout"], "S03 ambience continued (S04 source is digital silence: timelapse)"
    if sid == "S05":
        src_clip, src_in, note = s["clip"], 5.0, "replaced: same-clip sanctum ambience 5.0s+ (S05 speech indicator .54)"
    if sid == "S06":
        src_in = 5.0 + starts["S05"][1] / FPS; note = "sanctum ambience, continuous with S05"
    seg = read_src(src_clip, src_in - XF, dur + 2 * XF)
    filt = []
    if "WIND" in ana[sid]["flags"]:
        seg = hp(seg); filt.append("HP150")
    lvl = rms_db(seg)
    g = 0.0 if lvl < -90 else (TARGET_RMS - lvl + OFFSET.get(sid, 0.0))
    g = min(g, MAX_BOOST)   # quiet sources stay quieter: boosting them only lifts mic hiss
    seg = seg * 10 ** (g / 20)
    # equal-power fades over the crossfade handles
    k = int(XF * SR); ramp = np.sin(np.linspace(0, np.pi / 2, 2 * k)) ** 2
    seg[: 2 * k] *= np.sqrt(ramp)[:, None]; seg[-2 * k:] *= np.sqrt(ramp[::-1])[:, None]
    i0 = int(round((a0 - XF) * SR))
    j0, j1 = max(0, i0), min(total, i0 + len(seg))
    mix[j0:j1] += seg[j0 - i0: j1 - i0]
    log.append(dict(shot=sid, timeline_s=f"{a0:.3f}-{a0 + dur:.3f}", source=f"{src_clip}@{src_in:.2f}s", treatment=note,
                    filters="+".join(filt) or "none", gain_db=round(g, 1), src_rms_db=round(lvl, 1)))

# head/tail fades
h = int(0.25 * SR); tl = int(1.2 * SR)
mix[:h] *= np.linspace(0, 1, h)[:, None]; mix[-tl:] *= np.linspace(1, 0, tl)[:, None] ** 2
pre = os.path.join(AD, "mix_pre.wav"); sf.write(pre, mix.astype(np.float32), SR, subtype="FLOAT")

# 2-pass loudnorm to -14 LUFS / -1 dBTP
p1 = subprocess.run(["ffmpeg", "-hide_banner", "-i", pre, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                    capture_output=True, text=True).stderr
js = json.loads(p1[p1.rindex("{"): p1.rindex("}") + 1])
out = os.path.join(AD, "mix.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af",
                f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}"
                f":measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,aresample={SR}",
                "-c:a", "pcm_s24le", out], check=True)
with open(os.path.join(ROOT, "assets", "audio_mix_log.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(log[0].keys())); w.writeheader(); w.writerows(log)
print(f"timeline {t} frames = {t / FPS:.3f}s ; loudnorm pass1 input I={js['input_i']} TP={js['input_tp']}")
for r in log: print(r)
