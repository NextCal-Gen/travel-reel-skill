"""On-screen text design system (v7). No boxes by default.
 - STYLES: title, clean, editorial, location, chip, kinetic (macOS system fonts only).
 - choose_zone(): calmest area of the shot (low texture, stable over time) inside the Instagram safe area.
 - choose_colors(): palette-derived text + accent colours that pass worst-frame WCAG contrast
   (4.5:1 body, 3:1 large >= 64 px bold), preferring harmonious tints over plain white; a feathered
   local scrim (never a box) is added only if nothing passes.
 - render(): composite a styled overlay at time t (fades, rise, kinetic word pops).
 - Emoji: any space-separated word made of emoji is drawn in colour (Apple Color Emoji, rendered at its
   160 px bitmap strike and scaled), sized to the text, popping with the words. Never put a colon in
   caption copy (user style: use " - " if a break is needed).
Frames are display-referred RGB float32 [0,1], 1080x1920."""
import math
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
SAFE = (70, int(0.14 * H), W - 70, int(0.80 * H))          # x0, y0, x1, y1 (Instagram UI safe area)
F = {"futura": "/System/Library/Fonts/Supplemental/Futura.ttc", "avenir": "/System/Library/Fonts/Avenir Next.ttc",
     "didot": "/System/Library/Fonts/Supplemental/Didot.ttc", "optima": "/System/Library/Fonts/Optima.ttc"}
STYLES = {
    # font, index, size, tracking(px), upper, line_h, align, glow(alpha, blur), large_text
    "title":     dict(font="futura", idx=2, size=104, track=-1, upper=False, lh=1.02, align="center", glow=(0.32, 18), large=True),
    "clean":     dict(font="avenir", idx=2, size=56,  track=0,  upper=False, lh=1.12, align="center", glow=(0.30, 10), large=False),
    "editorial": dict(font="didot",  idx=1, size=70,  track=0,  upper=False, lh=1.05, align="center", glow=(0.30, 12), large=True,
                      kicker=dict(font="avenir", idx=5, size=35, track=7, upper=True)),
    "location":  dict(font="avenir", idx=2, size=45,  track=6,  upper=True,  lh=1.1,  align="left",   glow=(0.35, 8),  large=False, pin=True),
    "chip":      dict(font="avenir", idx=5, size=48,  track=1,  upper=False, lh=1.1,  align="left",   glow=(0.0, 0),   large=False, chip=True),
    "kinetic":   dict(font="futura", idx=2, size=78,  track=0,  upper=False, lh=1.05, align="center", glow=(0.30, 14), large=True),
}
_fc = {}
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_SCALE = 1.12          # emoji height relative to the font size (matches cap height + descender visually)
_ec = {}


def is_emoji(w):
    return any(ord(c) >= 0x1F000 or 0x2600 <= ord(c) <= 0x27BF for c in w)


def emoji_img(e, px):
    """RGBA PIL image of emoji sequence e, px tall (cached)."""
    k = (e, px)
    if k not in _ec:
        f = ImageFont.truetype(EMOJI_FONT, 160)
        im = Image.new("RGBA", (200 * max(1, len(e)), 200), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), e, font=f, embedded_color=True)
        im = im.crop(im.getbbox())
        _ec[k] = im.resize((max(1, round(im.width * px / im.height)), px), Image.LANCZOS)
    return _ec[k]


def font(name, idx, size):
    k = (name, idx, size)
    if k not in _fc: _fc[k] = ImageFont.truetype(F[name], size, index=idx)
    return _fc[k]


def ease(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
def back_out(x, s=1.7): x = np.clip(x, 0, 1) - 1; return 1 + x * x * ((s + 1) * x + s)


# ---------------- colour science helpers ----------------
def srgb_lin(c): c = np.asarray(c, np.float64); return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def rel_lum(rgb): l = srgb_lin(rgb); return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]
def contrast(l1, l2): a, b = max(l1, l2), min(l1, l2); return (a + 0.05) / (b + 0.05)


def _oklab(rgb):
    from lib_color import rgb_to_oklab
    return rgb_to_oklab(np.asarray(rgb, np.float64).reshape(-1, 3))


def _rgb(lab):
    from lib_color import oklab_to_rgb
    return np.clip(oklab_to_rgb(np.asarray(lab, np.float64).reshape(-1, 3)), 0, 1)


def palette(frame, k=5):
    small = cv2.resize(frame, (108, 192), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
    _, lab, cen = cv2.kmeans(small, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3), 3, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lab.ravel(), minlength=k) / len(lab)
    order = np.argsort(-share)
    return cen[order], share[order]


def candidates(pal):
    """Harmonious text colours derived from the shot palette (+ neutral fallbacks)."""
    labs = _oklab(pal); C = np.hypot(labs[:, 1], labs[:, 2]); h = np.arctan2(labs[:, 2], labs[:, 1])
    out = []
    accent_i = int(np.argmax(C))
    for i in [accent_i] + [j for j in range(len(pal)) if j != accent_i]:
        cc = min(C[i], 0.06)
        out.append(("tint", _rgb([[0.95, cc * np.cos(h[i]), cc * np.sin(h[i])]])[0]))      # light pastel of the shot's colour
    out.append(("warm white", np.array([1.0, 0.972, 0.925])))
    for i in [accent_i, 0]:
        cc = min(C[i], 0.09)
        out.append(("deep", _rgb([[0.24, cc * np.cos(h[i]), cc * np.sin(h[i])]])[0]))      # deep shade for bright backgrounds
    acc_c = max(C[accent_i], 0.12)
    accent = _rgb([[0.82, acc_c * np.cos(h[accent_i]), acc_c * np.sin(h[accent_i])]])[0]
    return out, accent


# ---------------- layout ----------------
def layout(text, st, maxw=900):
    f = font(st["font"], st["idx"], st["size"]); txt = text.upper() if st["upper"] else text
    words = txt.split(" ")
    def ww(w):
        if is_emoji(w): return emoji_img(w, int(st["size"] * EMOJI_SCALE)).width
        return sum(f.getlength(c) for c in w) + st["track"] * max(len(w) - 1, 0)
    def wl(s):
        ws = s.split(" "); return sum(ww(w) for w in ws) + (len(ws) - 1) * (f.getlength(" ") + st["track"])
    lines = [txt]
    if wl(txt) > maxw:
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:]); m = max(wl(a), wl(b))
            if best is None or m < best[0]: best = (m, [a, b])
        lines = best[1]
        if best[0] > maxw and st["size"] > 24:     # even the best 2-line split is too wide: shrink 7% and retry
            return layout(text, dict(st, size=int(st["size"] * 0.93)), maxw)
    asc, desc = f.getmetrics(); lh = int((asc + desc) * st["lh"])
    bw = max(wl(l) for l in lines); bh = lh * len(lines)
    kick_h = 0
    if st.get("kicker"): kick_h = int(st["kicker"]["size"] * 1.9)
    pin_w = int(st["size"] * 1.25) if st.get("pin") else 0
    pad = (28, 18) if st.get("chip") else (0, 0)
    return dict(f=f, lines=lines, lh=lh, bw=bw + pin_w + 2 * pad[0], bh=bh + kick_h + 2 * pad[1], kick_h=kick_h,
                pin_w=pin_w, pad=pad, wl=wl, ww=ww, asc=asc, st=st)


ZONES = {"center": [0.22, 0.30, 0.38, 0.62, 0.70], "left": [0.66, 0.72, 0.26, 0.20]}


def box_for(lay, st, zy):
    bw, bh = lay["bw"], lay["bh"]
    x0 = (W - bw) / 2 if st["align"] == "center" else SAFE[0] + 10
    y0 = zy * H - bh / 2
    y0 = float(np.clip(y0, SAFE[1], SAFE[3] - bh))
    return int(x0), int(y0), int(x0 + bw), int(y0 + bh)


def texture(frames, box):
    x0, y0, x1, y1 = box; s = []
    for fr in frames:
        g = cv2.cvtColor((fr[y0:y1, x0:x1] * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
        s.append(np.mean(np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))) + g.std() * 0.5)
    return float(np.mean(s) + np.std(s))


def local_colors(bg):
    """Colour candidates from the pixels BEHIND the text (analogous harmony) + a complementary accent."""
    px = bg[:: max(1, len(bg) // 6000)].astype(np.float32)
    _, lab, cen = cv2.kmeans(px, 3, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1e-3), 2, cv2.KMEANS_PP_CENTERS)
    dom = cen[np.argmax(np.bincount(lab.ravel(), minlength=3))]
    L0, a0, b0 = _oklab(dom)[0]; C0 = float(np.hypot(a0, b0)); h0 = float(np.arctan2(b0, a0))
    def lch(L, C, h): return _rgb([[L, C * np.cos(h), C * np.sin(h)]])[0]
    cands = [("deep " + ("tone" if C0 > 0.03 else "ink"), lch(0.27, min(max(C0, 0.04), 0.085), h0)),   # navy on sky, forest on leaves
             ("light tint", lch(0.965, min(C0, 0.035), h0)),
             ("warm white", np.array([1.0, 0.972, 0.925])),
             ("ink", np.array([0.11, 0.12, 0.14]))]
    hc = h0 + np.pi                                                                                     # complementary hue
    bgL = float(np.percentile(rel_lum(bg), 95)); bgD = float(np.percentile(rel_lum(bg), 5))
    accent = None
    for L in (np.arange(0.62, 0.30, -0.02) if bgL > 0.35 else np.arange(0.72, 0.98, 0.02)):
        c = lch(float(L), 0.16, hc); lc = float(rel_lum(c))
        if (contrast(lc, bgL) if bgL > 0.35 else contrast(lc, bgD)) >= 3.0: accent = c; break
    return cands, accent, dict(L=L0, C=C0, hue_deg=float(np.degrees(h0)) % 360)


def choose(frames, text, style, zone=None):
    """Pick zone + colours for an overlay given its background frames (list of HxWx3 float)."""
    st = STYLES[style]; lay = layout(text, st)
    zlist = [zone] if zone is not None else ZONES["left" if st["align"] == "left" else "center"]
    thr = 3.0 if st["large"] else 4.5
    best = None
    for zy in zlist:
        box = box_for(lay, st, zy); tex = texture(frames, box)
        bg = np.concatenate([fr[box[1]:box[3], box[0]:box[2]].reshape(-1, 3) for fr in frames])
        L = rel_lum(bg); lo, hi = np.percentile(L, 5), np.percentile(L, 95)
        cands, accent, info = local_colors(bg)
        for rank, (kind, col) in enumerate(cands):
            lt = float(rel_lum(col))
            cr = contrast(lt, hi) if lt > np.median(L) else contrast(lt, lo)   # worst case against the brightest/darkest bg
            if cr >= thr:
                score = tex + rank * 6.0        # calm area first, then harmony order
                if best is None or score < best["score"]:
                    best = dict(zone=zy, box=box, color=col, kind=kind, contrast=cr, texture=tex, score=score, scrim=0.0,
                                accent=accent if accent is not None else col, bg=info)
    if best is None:   # nothing passes: calmest zone, warm white, feathered scrim strong enough
        zy = min(zlist, key=lambda z: texture(frames, box_for(lay, st, z))); box = box_for(lay, st, zy)
        col = np.array([1.0, 0.972, 0.925])
        bg = np.concatenate([fr[box[1]:box[3], box[0]:box[2]].reshape(-1, 3) for fr in frames])
        for s in np.arange(0.15, 0.71, 0.05):
            cr = contrast(float(rel_lum(col)), float(np.percentile(rel_lum(bg * (1 - s)), 95)))
            if cr >= thr: break
        best = dict(zone=zy, box=box, color=col, kind="warm white + scrim", contrast=cr, texture=texture(frames, box),
                    scrim=float(s), accent=col, bg={})
    best.update(style=style, text=text, layout=lay)
    return best


# ---------------- rendering ----------------
def _draw_text(d, x, y, s, f, track, fill):
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill); x += f.getlength(ch) + track
    return x


def render(frame, spec, t, dur, fade=0.22):
    """Composite spec (from choose()) onto frame at local time t within [0, dur]."""
    lay = spec["layout"]; st = lay.get("st", STYLES[spec["style"]]); x0, y0, x1, y1 = spec["box"]
    a = float(ease(t / fade) * ease((dur - t) / fade))
    if a <= 0.001: return frame
    rise = 16 * (1 - ease(t / fade))
    col = tuple(int(c * 255) for c in spec["color"]); acc = tuple(int(c * 255) for c in spec["accent"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dg = ImageDraw.Draw(glow)
    dark_text = rel_lum(spec["color"]) < 0.3
    gcol = (255, 255, 255) if dark_text else (0, 0, 0)
    px, py = x0 + lay["pad"][0], y0 + lay["pad"][1] + rise
    if st.get("chip"):
        bgc = (255, 255, 255, int(40 * a)) if not dark_text else (255, 255, 255, int(110 * a))
        if not dark_text: bgc = (0, 0, 0, int(55 * a))
        d.rounded_rectangle([x0, y0 + rise, x1, y1 + rise], radius=(y1 - y0) // 2, fill=bgc, outline=col + (int(200 * a),), width=2)
    if st.get("kicker"):
        k = st["kicker"]; kf = font(k["font"], k["idx"], k["size"])
        kt = spec.get("kicker", "").upper()
        kw = sum(kf.getlength(c) for c in kt) + k["track"] * max(len(kt) - 1, 0)
        _draw_text(dg, (W - kw) / 2 + 1, py + 2, kt, kf, k["track"], gcol + (int(255 * st["glow"][0] * a),))
        _draw_text(d, (W - kw) / 2, py, kt, kf, k["track"], acc + (int(255 * a),))
        py += lay["kick_h"]
    if st.get("pin"):
        r = st["size"] * 0.30; cx, cy = px + r, py + lay["lh"] * 0.45
        for dd, fill in ((dg, gcol + (int(255 * st["glow"][0] * a),)), (d, acc + (int(255 * a),))):
            dd.ellipse([cx - r, cy - r * 1.05, cx + r, cy + r * 0.95], fill=fill)
            dd.polygon([(cx - r * 0.72, cy + r * 0.45), (cx + r * 0.72, cy + r * 0.45), (cx, cy + r * 1.9)], fill=fill)
        d.ellipse([cx - r * 0.38, cy - r * 0.42, cx + r * 0.38, cy + r * 0.34], fill=(0, 0, 0, 0))
        px += lay["pin_w"]
    acc_words = set(w.upper() for w in spec.get("accent_words", []))
    words_all = [w for line in lay["lines"] for w in line.split(" ")]
    n_words = len(words_all); wi = 0
    for k, line in enumerate(lay["lines"]):
        lw = lay["wl"](line)
        x = (W - lw) / 2 if st["align"] == "center" else px
        y = py + k * lay["lh"]
        for w in line.split(" "):
            wa = a
            if spec["style"] == "kinetic":            # word-by-word pop with overshoot
                tw = (t - 0.10 * wi) / 0.28; wa = a * float(np.clip(tw * 1.6, 0, 1))
                sc = float(back_out(tw)) if tw < 1 else 1.0
            else: sc = 1.0
            fill = acc if w.strip(".,!?…“”\"").upper() in acc_words else col
            ww = lay["ww"](w)
            if wa > 0.01 and is_emoji(w):              # colour emoji, scaled with the pop, centred on the cap height
                if sc > 0.05:
                    e = emoji_img(w, max(4, int(st["size"] * EMOJI_SCALE * sc)))
                    ea = e.copy(); ea.putalpha(ea.getchannel("A").point(lambda v: int(v * wa)))
                    cy = y + lay["asc"] * 0.62
                    img.alpha_composite(ea, (int(x + (ww - e.width) / 2), int(cy - e.height / 2)))
            elif wa > 0.01:
                if sc != 1.0 and sc > 0.05:
                    fs = max(8, int(st["size"] * sc)); f2 = font(st["font"], st["idx"], fs)
                    dx = (ww - ww * sc) / 2; dy = (lay["lh"] - lay["lh"] * sc) / 2
                    _draw_text(dg, x + dx + 2, y + dy + 4, w, f2, st["track"] * sc, gcol + (int(255 * st["glow"][0] * wa),))
                    _draw_text(d, x + dx, y + dy, w, f2, st["track"] * sc, fill + (int(255 * wa),))
                elif sc > 0.05:
                    _draw_text(dg, x + 2, y + 4, w, lay["f"], st["track"], gcol + (int(255 * st["glow"][0] * wa),))
                    _draw_text(d, x, y, w, lay["f"], st["track"], fill + (int(255 * wa),))
            x += ww + lay["f"].getlength(" ") + st["track"]; wi += 1
    out = frame.copy()
    if spec.get("scrim", 0) > 0:   # feathered local darkening, never a hard box
        m = np.zeros((H, W), np.float32)
        cv2.rectangle(m, (x0 - 40, int(y0 - 30)), (x1 + 40, int(y1 + 30)), 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 45) * spec["scrim"] * a
        out = out * (1 - m[..., None])
    if st["glow"][0] > 0:
        g = np.asarray(glow.filter(ImageFilter.GaussianBlur(st["glow"][1]))).astype(np.float32) / 255
        out = out * (1 - g[..., 3:4]) + g[..., :3] * g[..., 3:4]
    o = np.asarray(img).astype(np.float32) / 255
    return out * (1 - o[..., 3:4]) + o[..., :3] * o[..., 3:4]
