"""v6 (user request): burned-in on-screen text across the reel (hook, captions, CTA).
Explicit user override of the CLAUDE.md "no burned-in text" rule; a clean (no-text) version is kept.
Composited on the 10-bit graded timeline (work/timeline_prores.mov) through the verified decode
(limited YUV -> 16-bit RGB) and encode (zscale -> yuv422p10le limited BT.709) paths; colours untouched.
Style matches the map labels: Avenir Next Demi Bold, warm white, soft shadow, soft dark scrim for
legibility on bright skies; fade + rise in, fade out. Contrast is MEASURED per overlay (WCAG ratio).
Outputs: work/timeline_text.mov (ProRes 422 HQ 10-bit), previews/rough_cut_v<N>.mp4 (muted),
         assets/text_overlays.csv (timings, contrast)
Usage: 92_text_overlays.py <version> [--still t out.jpg]"""
import csv, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, to_rgb

W, H, FPS = 1080, 1920, 30
FONT_PATH, FONT_IDX = "/System/Library/Fonts/Avenir Next.ttc", 2      # Demi Bold
WHITE = (250, 248, 242); AMBER = (255, 200, 120)   # lighter gold than the map amber: 4.33 -> >=4.5:1 on worst frame
SAFE_Y0, SAFE_Y1, MAXW = int(0.14 * H), int(0.80 * H), 900
Y_CENTER = int(0.25 * H)

# (t_in, t_out, text, size, accent_word)   v5 timeline: S00 0-5 | MAP 5-9 | S01 9-10.8 | S02 10.8-12.6 |
# S03 12.6-14.2 | S05 14.2-15.8 | S06 15.8-17.8 | S07 17.8-19.8 | S08 19.8-21.9 | S10 21.9-25.3 | S11 25.3-28.7
OVERLAYS = [
    (0.15, 2.45, "We rode 60+ km for breakfast…", 76, None),          # 60+ km = estimated road route (62.5 km)
    (2.55, 4.95, "…to a hilltop temple near Kanakapura", 76, None),
    (9.05, 10.75, "Lilies at the summit", 58, None),
    (10.85, 12.55, "Parked with a view", 58, None),
    (12.65, 14.15, "Bettada Shri Siddeshwara Siddappaji Temple", 54, None),
    (19.85, 21.85, "Worth every kilometre", 60, None),
    (21.95, 25.25, "The ride back: a river crossing", 58, None),
    (25.35, 27.00, "Save this for your next weekend ride", 58, None),
    (27.05, 28.65, "DM “RIDE” to get the details", 62, "“RIDE”"),
]
FADE_IN, FADE_OUT, RISE = 0.25, 0.20, 14
SCRIM_A = 205   # v6 checks (worst frame per line): 45% backing 2.0-4.4:1; 72% 3.2-4.1:1; -> 80% for >= 4.5:1


def ease(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)


_fonts = {}
def font(sz):
    if sz not in _fonts: _fonts[sz] = ImageFont.truetype(FONT_PATH, sz, index=FONT_IDX)
    return _fonts[sz]


def wrap(text, f):
    """Single line if it fits; otherwise the most BALANCED 2-line split (no stranded last word);
    greedy fallback only if no 2-line split fits MAXW."""
    words = text.split(" ")
    if f.getlength(text) <= MAXW: return [text]
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        m = max(f.getlength(a), f.getlength(b))
        if m <= MAXW and (best is None or m < best[0]): best = (m, [a, b])
    if best: return best[1]
    return greedy(text, f)


def greedy(text, f):
    words, lines, cur = text.split(" "), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if f.getlength(t) <= MAXW: cur = t
        else: lines.append(cur); cur = w_
    lines.append(cur)
    return lines


def layout(text, sz):
    f = font(sz); lines = wrap(text, f)
    asc, desc = f.getmetrics(); lh = int((asc + desc) * 1.12)
    bh = lh * len(lines); bw = max(f.getlength(l) for l in lines)
    y0 = Y_CENTER - bh // 2
    return f, lines, lh, bw, bh, y0


def overlay_rgba(t):
    """Returns (rgba float32 HxWx4 or None, active overlay index)."""
    for i, (a, b, text, sz, accent) in enumerate(OVERLAYS):
        if a <= t <= b:
            al = ease((t - a) / FADE_IN) * ease((b - t) / FADE_OUT)
            rise = RISE * (1 - ease((t - a) / FADE_IN))
            f, lines, lh, bw, bh, y0 = layout(text, sz); y0 += rise
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            # soft scrim behind the block
            scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ds = ImageDraw.Draw(scrim)
            pad_x, pad_y = 50, 36   # v6: wider so the blurred edge falls off outside the glyphs (worst-frame contrast)
            ds.rounded_rectangle([W / 2 - bw / 2 - pad_x, y0 - pad_y, W / 2 + bw / 2 + pad_x, y0 + bh + pad_y],
                                 radius=28, fill=(0, 0, 0, int(SCRIM_A * al)))
            img.alpha_composite(scrim.filter(ImageFilter.GaussianBlur(14)))
            # shadow + text
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dsh = ImageDraw.Draw(sh)
            tx = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dtx = ImageDraw.Draw(tx)
            for k, line in enumerate(lines):
                x = W / 2 - f.getlength(line) / 2; y = y0 + k * lh
                for word in line.split(" "):
                    col = AMBER if (accent and word.strip(".,") == accent) else WHITE
                    dsh.text((x + 2, y + 3), word, font=f, fill=(0, 0, 0, int(210 * al)))
                    dtx.text((x, y), word, font=f, fill=col + (int(255 * al),))
                    x += f.getlength(word + " ")
            img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4))); img.alpha_composite(tx)
            return np.asarray(img).astype(np.float32) / 255.0, i
    return None, None


def composite(rgb, ov):
    a = ov[..., 3:4]
    return rgb * (1 - a) + ov[..., :3] * a


def rel_lum(rgb):
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def decode_frames(path):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", to_rgb(W, H, "limited"),
                          "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"], stdout=subprocess.PIPE)
    n = W * H * 3 * 2
    while True:
        b = p.stdout.read(n)
        if len(b) < n: break
        yield np.frombuffer(b, "<u2").reshape(H, W, 3).astype(np.float32) / 65535


src = os.path.join(ROOT, "work", "timeline_prores.mov")
if "--still" in sys.argv:
    t = float(sys.argv[sys.argv.index("--still") + 1]); out = sys.argv[sys.argv.index("--still") + 2]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", src, "-frames:v", "1", "-vf", to_rgb(W, H, "limited"),
                          "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"], capture_output=True, check=True).stdout
    rgb = np.frombuffer(raw, "<u2").reshape(H, W, 3).astype(np.float32) / 65535
    ov, _ = overlay_rgba(t)
    if ov is not None: rgb = composite(rgb, ov)
    Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out, quality=92); print(out); sys.exit()

ver = sys.argv[1] if len(sys.argv) > 1 else "6"
dst = os.path.join(ROOT, "work", "timeline_text.mov")
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-vf", "setparams=range=pc:color_primaries=bt709:color_trc=bt709:colorspace=gbr,"
                               "zscale=range=limited:matrix=709:primaries=709:transfer=709,format=yuv422p10le",
                        "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le",
                        "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", dst],
                       stdin=subprocess.PIPE)
stats = {}
for i, rgb in enumerate(decode_frames(src)):
    t = i / FPS
    ov, k = overlay_rgba(t)
    if ov is not None:
        out = composite(rgb, ov)
        a = ov[..., 3]
        if a.max() > 0.95:   # fully faded in: glyph vs backing contrast (accent words measured separately)
            textpx = (a > 0.9) & (ov[..., :3].max(-1) > 0.5)            # ALL text pixels (white + accent)
            white = textpx & (ov[..., :3].min(-1) > 0.9)
            acc = textpx & ((ov[..., 0] - ov[..., 2]) > 0.4)              # amber accent by colour (not grey AA edges over the shadow)
            ys, xs = np.where(textpx)
            if len(ys):
                y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
                sl = (slice(y0, y1 + 1), slice(x0, x1 + 1))
                import cv2 as _cv
                halo = _cv.dilate((ov[..., 3] > 0.05).astype(np.uint8) & (ov[..., :3].max(-1) > 0.3).astype(np.uint8),
                                  np.ones((7, 7), np.uint8)).astype(bool)          # text incl. anti-aliased edges (+3 px)
                bg = (~halo[sl]) & (a[sl] > 0.5)                          # backing pixels only
                Lb = np.percentile(rel_lum(out[sl][bg]), 90)
                crs = [(np.percentile(rel_lum(out[m]), 10) + 0.05) / (Lb + 0.05) for m in (white, acc) if m.sum() > 50]
                if not crs:      # mid-fade frame without enough fully-opaque glyph pixels: nothing to measure
                    rgb = out; enc.stdin.write((np.clip(rgb, 0, 1) * 65535 + 0.5).astype("<u2").tobytes()); continue
                cr = min(crs)
                s = stats.setdefault(k, dict(min_contrast=99.0, frames=0, box=(int(x0), int(y0), int(x1), int(y1))))
                s["min_contrast"] = min(s["min_contrast"], float(cr)); s["frames"] += 1
        rgb = out
    enc.stdin.write((np.clip(rgb, 0, 1) * 65535 + 0.5).astype("<u2").tobytes())
enc.stdin.close(); enc.wait()

rows = []
for k, (a, b, text, sz, acc) in enumerate(OVERLAYS):
    s = stats.get(k, {}); bx = s.get("box", (0, 0, 0, 0))
    rows.append(dict(t_in=a, t_out=b, text=text, size=sz, min_contrast_ratio=round(s.get("min_contrast", 0), 2),
                     wcag_AA_large_3_0=s.get("min_contrast", 0) >= 3.0, passes_4_5=s.get("min_contrast", 0) >= 4.5, glyph_box=bx,
                     in_safe_area=bool(bx[1] >= SAFE_Y0 and bx[3] <= SAFE_Y1 and bx[0] >= 54 and bx[2] <= W - 54)))
with open(os.path.join(ROOT, "assets", "text_overlays.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(f"{r['t_in']:5.2f}-{r['t_out']:5.2f} worst-frame contrast {r['min_contrast_ratio']:5.2f}:1  AA-large(3:1) {'pass' if r['wcag_AA_large_3_0'] else 'FAIL'}  4.5:1 {'pass' if r['passes_4_5'] else 'FAIL'}  safe={r['in_safe_area']}  {r['text']}")

prev = os.path.join(ROOT, "previews", f"rough_cut_v{ver}.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dst, "-vf", "scale=in_range=tv:out_range=tv,format=yuv420p,limiter=min=16:max=235:planes=1",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", "30",
                "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-an", "-movflags", "+faststart", prev], check=True)
print("preview", prev)
