"""v7: procedurally SYNTHESISED sound effects for on-screen text and camera moves.
No sample files -> no licensing issues (safe for the public skill repo).
  pop     text appearing (pitch-dropping sine + transient)        ~90 ms
  tick    kinetic word-by-word pops                               ~25 ms
  pin     location tag (small bell: inharmonic partials)          ~1.2 s
  whoosh  fast pans / spins (band-pass noise sweep, L->R pan)     ~0.6 s
  rise    hook build-up (noise + rising sine)                     ~0.8 s
  thud    title landing (low sine + noise burst)                  ~0.3 s
Output: assets/sfx/<name>.wav (48 kHz stereo, 24-bit, peak -3 dBFS), assets/sfx/sfx_demo.wav
(all sounds 0.7 s apart) and assets/sfx/sfx_report.csv (measured duration, peak, centroid)."""
import csv, os, sys
import numpy as np, scipy.signal as sg, soundfile as sf
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

SR = 48000
OUT = os.path.join(ROOT, "assets", "sfx"); os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def t_(d): return np.arange(int(d * SR)) / SR
def env_ad(n, a, d):  # attack/decay exponential envelope
    t = np.arange(n) / SR; e = np.minimum(t / max(a, 1e-4), 1.0) * np.exp(-np.maximum(t - a, 0) / d); return e
def pink(n):
    w = rng.standard_normal(n); b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
    return sg.lfilter(b, a, w)
def norm(x, peak_db=-3.0): return x / (np.abs(x).max() + 1e-12) * 10 ** (peak_db / 20)
def stereo(x, pan=0.0):  # pan -1..1 (constant power), pan may be an array
    p = (np.asarray(pan) + 1) * np.pi / 4; return np.stack([x * np.cos(p), x * np.sin(p)], 1)


def pop():
    t = t_(0.09); f = 250 + 650 * np.exp(-t / 0.012)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(len(t), 0.001, 0.025)
    click = sg.lfilter(*sg.butter(2, 2500, "high", fs=SR), rng.standard_normal(len(t))) * env_ad(len(t), 0.0003, 0.002) * 0.4
    return stereo(norm(body + click, -4))


def tick():
    t = t_(0.025); x = sg.lfilter(*sg.butter(2, [2200, 5200], "band", fs=SR), rng.standard_normal(len(t))) * env_ad(len(t), 0.0003, 0.004)
    return stereo(norm(x, -8))


def pin():
    t = t_(1.2); f0 = 1318.5
    x = sum(a * np.sin(2 * np.pi * f0 * r * t) * env_ad(len(t), 0.002, d)
            for r, a, d in ((1.0, 1.0, 0.55), (2.76, 0.45, 0.25), (5.40, 0.22, 0.12), (8.93, 0.10, 0.06)))
    return stereo(norm(x, -6))


def whoosh():
    t = t_(0.6); n = pink(len(t)); out = np.zeros_like(n)
    fc = np.interp(t, [0, 0.28, 0.6], [350, 2400, 600])        # resonant band sweeping up then down
    for i in range(0, len(t), 480):                             # block-wise time-varying band-pass
        b, a = sg.butter(2, [fc[i] * 0.6, min(fc[i] * 1.6, 20000)], "band", fs=SR)
        out[i:i + 480] = sg.lfilter(b, a, n[i:i + 480])
    e = np.interp(t, [0, 0.25, 0.6], [0, 1, 0]) ** 1.5
    return stereo(norm(out * e, -5), pan=np.interp(t, [0, 0.6], [-0.7, 0.7]))


def rise():
    t = t_(0.8); f = np.geomspace(200, 1200, len(t))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.35
    air = sg.lfilter(*sg.butter(2, 1500, "high", fs=SR), pink(len(t))) * 0.6
    e = (t / t[-1]) ** 2 * np.exp(-np.maximum(t - 0.74, 0) / 0.02)
    return stereo(norm((tone + air) * e, -6))


def thud():
    t = t_(0.3); body = np.sin(2 * np.pi * np.cumsum(np.interp(t, [0, 0.3], [75, 45])) / SR) * env_ad(len(t), 0.002, 0.09)
    hit = sg.lfilter(*sg.butter(2, 400, "low", fs=SR), rng.standard_normal(len(t))) * env_ad(len(t), 0.001, 0.02) * 0.5
    return stereo(norm(body + hit, -3))


SOUNDS = dict(pop=pop, tick=tick, pin=pin, whoosh=whoosh, rise=rise, thud=thud)
rows, demo = [], []
for name, fn in SOUNDS.items():
    x = fn().astype(np.float32)
    sf.write(os.path.join(OUT, f"{name}.wav"), x, SR, subtype="PCM_24")
    m = x.mean(1); S = np.abs(np.fft.rfft(m)); fr = np.fft.rfftfreq(len(m), 1 / SR)
    rows.append(dict(sound=name, duration_s=round(len(x) / SR, 3), peak_dbfs=round(20 * np.log10(np.abs(x).max()), 1),
                     spectral_centroid_hz=int((S * fr).sum() / (S.sum() + 1e-12)), clipped=bool(np.abs(x).max() >= 1.0)))
    demo += [x, np.zeros((int(0.7 * SR), 2), np.float32)]
sf.write(os.path.join(OUT, "sfx_demo.wav"), np.concatenate(demo), SR, subtype="PCM_24")
with open(os.path.join(OUT, "sfx_report.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(r)
