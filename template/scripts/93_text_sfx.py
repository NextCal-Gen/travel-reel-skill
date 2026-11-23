"""Phase 8: on-screen text (lib_text design system) + optional synthesised SFX, on the 10-bit timeline.
Generic: all trip data lives in two CSVs (no code edits per trip).

assets/overlays.csv   t_in,t_out,style,text,kicker,accent_words,sfx
    style        title | clean | editorial | location | chip | kinetic   (lib_text.STYLES)
    text         copy rules: emoji only where they add meaning, NO colons (use " - " if a break is needed),
                 facts only from the user or strong sources (assets/research.md)
    kicker       small line above an editorial title (optional)
    accent_words words drawn in the accent colour, separated by | (optional)
    sfx          pop | tick | pin | whoosh | rise | thud | ticks (one tick per word, kinetic) | empty
assets/sfx_cues.csv   t,sound,gain    extra cues not tied to text (camera turns, cuts). Optional.

Placement and colours are chosen per overlay by lib_text.choose() from 3 frames of the timeline
(calm zone in the safe area, colours from the pixels behind the text, worst-frame contrast >= 4.5:1,
3:1 for large text; feathered scrim only if nothing passes). Report: assets/overlay_report.csv.

Usage: 93_text_sfx.py <ver> [--src work/timeline_prores.mov] [--board]
  --board   cheap check: one still per overlay -> assets/overlay_board.jpg (no full render)
Outputs: work/timeline_text.mov (ProRes 422 HQ 10-bit), work/audio/sfx.wav (if any cue),
         previews/rough_cut_v<ver>.mp4 (muted) and previews/rough_cut_v<ver>_sfx.mp4 (if any cue)
Needs assets/sfx/*.wav from 94_sfx.py when cues are used."""
import csv, os, subprocess, sys
import cv2, numpy as np, soundfile as sf
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb
import lib_text as T

W, H, FPS, SR = T.W, T.H, 30, 48000
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ver = args[0] if args else "1"
src = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else os.path.join(ROOT, "work", "timeline_prores.mov")
ov = [r for r in csv.DictReader(open(os.path.join(ROOT, "assets", "overlays.csv"), encoding="utf-8"))]
for r in ov:
    r["t_in"], r["t_out"] = float(r["t_in"]), float(r["t_out"])
    assert ":" not in r["text"] and ":" not in r.get("kicker", ""), f"no colons in caption copy: {r['text']!r}"
    assert r["style"] in T.STYLES, r["style"]
dur_tl = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                              capture_output=True, text=True).stdout)


def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-vf", to_rgb(W, H, "limited"),
                          "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<u2").reshape(H, W, 3).astype(np.float32) / 65535


specs, rep = [], []
for r in ov:
    a, b = r["t_in"], r["t_out"]
    sp = T.choose([grab(a + (b - a) * f) for f in (0.15, 0.5, 0.85)], r["text"], r["style"])
    if r.get("kicker"): sp["kicker"] = r["kicker"]
    if r.get("accent_words"): sp["accent_words"] = r["accent_words"].split("|")
    specs.append(sp)
    rep.append(dict(t_in=a, t_out=b, style=r["style"], text=r["text"], zone_y=sp["zone"], color=sp["kind"],
                    color_rgb=[round(float(c), 3) for c in sp["color"]], worst_contrast=round(float(sp["contrast"]), 2),
                    scrim=round(float(sp["scrim"]), 2), shown_s=round(b - a, 2), min_1_5s=(b - a) >= 1.5))
with open(os.path.join(ROOT, "assets", "overlay_report.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rep[0].keys())); w.writeheader(); w.writerows(rep)
for x in rep: print(x)

if "--board" in sys.argv:
    tiles = []
    for r, sp in zip(ov, specs):
        lt = min(1.0, (r["t_out"] - r["t_in"]) * 0.6)
        im = T.render(grab(r["t_in"] + lt), sp, lt, r["t_out"] - r["t_in"])
        tiles.append(cv2.resize((np.clip(im, 0, 1) * 255).astype(np.uint8), (360, 640), interpolation=cv2.INTER_AREA)[..., ::-1])
    while len(tiles) % 5: tiles.append(np.full_like(tiles[0], 30))
    board = np.vstack([np.hstack([np.pad(t, ((4, 4), (4, 4), (0, 0)), constant_values=255) for t in tiles[i:i + 5]])
                       for i in range(0, len(tiles), 5)])
    cv2.imwrite(os.path.join(ROOT, "assets", "overlay_board.jpg"), board, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("assets/overlay_board.jpg"); sys.exit()

# ---- full render on the 10-bit timeline (verified decode -> RGB 16-bit -> verified encode) ----
dst = os.path.join(ROOT, "work", "timeline_text.mov")
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", to_rgb(W, H, "limited"), "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
                       stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-vf", "setparams=range=pc:color_primaries=bt709:color_trc=bt709:colorspace=gbr,"
                               "zscale=range=limited:matrix=709:primaries=709:transfer=709,format=yuv422p10le",
                        "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le",
                        "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", dst],
                       stdin=subprocess.PIPE)
n, i = W * H * 6, 0
while True:
    buf = dec.stdout.read(n)
    if len(buf) < n: break
    rgb = np.frombuffer(buf, "<u2").reshape(H, W, 3).astype(np.float32) / 65535; t = i / FPS
    for r, sp in zip(ov, specs):
        if r["t_in"] <= t <= r["t_out"]: rgb = T.render(rgb, sp, t - r["t_in"], r["t_out"] - r["t_in"])
    enc.stdin.write((np.clip(rgb, 0, 1) * 65535 + 0.5).astype("<u2").tobytes()); i += 1
enc.stdin.close(); enc.wait(); print("text frames", i)

# ---- SFX track ----
cues = []
for r in ov:
    fx = (r.get("sfx") or "").strip()
    if fx == "ticks": cues += [(r["t_in"] + 0.10 * k, "tick", 0.9) for k in range(len(r["text"].split()))]   # matches lib_text kinetic stagger
    elif fx: cues.append((r["t_in"], fx, 0.9 if fx == "thud" else 0.8))
extra = os.path.join(ROOT, "assets", "sfx_cues.csv")
if os.path.exists(extra):
    cues += [(float(c["t"]), c["sound"], float(c.get("gain") or 0.7)) for c in csv.DictReader(open(extra))]
VF = "scale=in_range=tv:out_range=tv,format=yuv420p,limiter=min=16:max=235:planes=1"
TAGS = ["-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
X264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", "30"]
muted = os.path.join(ROOT, "previews", f"rough_cut_v{ver}.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dst, "-vf", VF, *X264, *TAGS, "-an", "-movflags", "+faststart", muted], check=True)
print(muted)
if cues:
    mix = np.zeros((int(np.ceil(dur_tl * SR)), 2), np.float32)
    for t, nm, g in cues:
        x, sr = sf.read(os.path.join(ROOT, "assets", "sfx", nm + ".wav"), dtype="float32"); assert sr == SR
        s = int(t * SR); e = min(s + len(x), len(mix)); mix[s:e] += x[:e - s] * g
    peak = float(np.abs(mix).max()); lim = 10 ** (-1.5 / 20)
    if peak > lim: mix *= lim / peak
    os.makedirs(os.path.join(ROOT, "work", "audio"), exist_ok=True)
    wav = os.path.join(ROOT, "work", "audio", "sfx.wav"); sf.write(wav, mix, SR, subtype="PCM_24")
    print(f"sfx: {len(cues)} cues, peak {20 * np.log10(max(np.abs(mix).max(), 1e-9)):.1f} dBFS")
    withfx = os.path.join(ROOT, "previews", f"rough_cut_v{ver}_sfx.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dst, "-i", wav, "-map", "0:v", "-map", "1:a", "-vf", VF, *X264, *TAGS,
                    "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", withfx], check=True)
    print(withfx)
