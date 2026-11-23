"""Phase 7.1: analyse each EDL shot's source audio (same in/out as the picture).
Measures (no listening possible, so these are indicators, reported as such):
  - RMS level (dBFS) and peak
  - wind/rumble ratio: energy < 150 Hz / total            (wind on a moving bike is low-frequency)
  - speech indicator: 2-8 Hz modulation of the 300-3400 Hz band envelope relative to 0.5-20 Hz
    (syllabic rhythm). > 0.45 = speech likely present -> flag for user review.
Output: work/audio/<id>.wav (48k stereo float), assets/audio_analysis.csv"""
import csv, os, subprocess, sys
import numpy as np, librosa, scipy.signal as sg
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_edl import load_edl

AD = os.path.join(ROOT, "work", "audio"); os.makedirs(AD, exist_ok=True)
rows = []
for s in load_edl():
    wav = os.path.join(AD, f"{s['id']}.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s['tin']:.3f}", "-t", f"{s['dur']:.3f}", "-i",
                    os.path.join(ROOT, "raw", s["clip"]), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", wav], check=True)
    y, sr = librosa.load(wav, sr=48000, mono=False)
    m = y.mean(0)
    rms = 20 * np.log10(np.sqrt((m ** 2).mean()) + 1e-12); peak = 20 * np.log10(np.abs(y).max() + 1e-12)
    S = np.abs(librosa.stft(m, n_fft=4096, hop_length=1024)) ** 2
    f = librosa.fft_frequencies(sr=sr, n_fft=4096)
    low = S[f < 150].sum() / (S.sum() + 1e-12)
    b, a = sg.butter(4, [300, 3400], btype="band", fs=sr)
    env = np.abs(sg.hilbert(sg.filtfilt(b, a, m)))
    env = sg.resample_poly(env, 1, 480)              # 100 Hz envelope
    env = env - env.mean()
    fe, pe = sg.welch(env, fs=100, nperseg=min(256, len(env)))
    sp = pe[(fe >= 2) & (fe <= 8)].sum() / (pe[(fe >= 0.5) & (fe <= 20)].sum() + 1e-12)
    rows.append(dict(id=s["id"], clip=s["clip"], dur=s["dur"], rms_dbfs=round(rms, 1), peak_dbfs=round(peak, 1),
                     wind_low_ratio=round(float(low), 3), speech_indicator=round(float(sp), 3),
                     flags=";".join(x for x in [("WIND" if low > 0.5 else ""), ("SPEECH?" if sp > 0.45 else ""),
                                                 ("QUIET" if rms < -45 else "")] if x)))
with open(os.path.join(ROOT, "assets", "audio_analysis.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(r["id"], r["rms_dbfs"], r["peak_dbfs"], r["wind_low_ratio"], r["speech_indicator"], r["flags"], "|", r["clip"][:24])
