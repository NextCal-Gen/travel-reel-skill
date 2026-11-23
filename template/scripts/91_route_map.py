"""Route-map insert (v4, user request): animated map of the ride, NO text (labels go in Instagram).
Data: OpenStreetMap (ODbL) via Overpass (roads/water, assets/map/osm_base.json) and OSRM routing
(assets/map/route_out.json Bengaluru centre -> temple; route_back.json temple -> river viewpoint -> Bengaluru).
The route is the likely ROAD route between the points, not a GPS track (clips carry no GPS).
Bengaluru point = generic city centre (12.9716, 77.5946), not any personal location.
Credit required in the post caption: "Map data © OpenStreetMap contributors".
Render: 3x supersampled base, eased push-in, amber route draw-on with glow, pin pops.
Output: work/shots/M01.mov (ProRes 422 HQ 10-bit, BT.709, 1080x1920, 30 fps).
v5 (user request): sequenced place labels BURNED IN on this insert only (explicit exception to the
CLAUDE.md "no burned-in text" rule): Bengaluru -> Siddappaji Temple -> River crossing -> Back to Bengaluru.
Font: Avenir Next Demi Bold (macOS system font), uppercase, tracked, soft shadow; safe area checked.
Usage: 91_route_map.py [--still t_seconds out.jpg]"""
import json, os, subprocess, sys
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

W, H, FPS, DUR, SS = 1080, 1920, 30, 4.0, 3   # v5: 4.0 s so the sequenced labels can be read
MD = os.path.join(ROOT, "assets", "map")
PTS = {"blr": (12.9716, 77.5946), "temple": (12.5900249, 77.3415824), "river": (12.6203035, 77.4071665)}
LAT0 = 12.78
# palette (BGR) - warm dark, sits with Look 2
BG = (22, 24, 28); BG2 = (14, 15, 18)
ROAD = {"motorway": ((84, 92, 100), 3.2), "trunk": ((76, 84, 92), 2.8), "primary": ((62, 68, 75), 2.2), "secondary": ((48, 52, 58), 1.6)}
WATER_FILL = (78, 62, 44); WATER_LINE = (120, 96, 66)
ROUTE = (64, 178, 255); ROUTE_BACK = (170, 220, 255); PIN = (64, 178, 255); WHITE = (245, 245, 245)


def ease(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
def ease_out(x): x = np.clip(x, 0, 1); return 1 - (1 - x) ** 3


def proj(lat, lon):
    return np.stack([np.asarray(lon) * np.cos(np.radians(LAT0)), -np.asarray(lat)], -1)


def route(name):
    c = np.array(json.load(open(os.path.join(MD, name)))["routes"][0]["geometry"]["coordinates"])
    return proj(c[:, 1], c[:, 0])


r_out, r_back = route("route_out.json"), route("route_back.json")
allp = np.vstack([r_out, r_back])
lo, hi = allp.min(0), allp.max(0); ctr = (lo + hi) / 2
span = hi - lo
# world -> canvas: fit route bbox into the central ~62% width / 58% height of the 9:16 frame
scale0 = min(W * 0.62 / span[0], H * 0.50 / span[1])   # v5: smaller + raised so labels clear Instagram's bottom UI
VCEN = 0.47
CW, CH = W * SS, H * SS


def to_canvas(p, scale):
    return (p - ctr) * scale * SS + np.array([CW / 2, CH * VCEN])


# ---------- static base layer at 3x (drawn once, at the widest view) ----------
def base_layer():
    img = np.zeros((CH, CW, 3), np.uint8); img[:] = BG
    yy, xx = np.mgrid[0:CH, 0:CW]
    vig = np.clip(np.hypot((xx - CW / 2) / (CW * 0.7), (yy - CH / 2) / (CH * 0.7)), 0, 1)[..., None]
    img = (img * (1 - vig) + np.array(BG2) * vig).astype(np.uint8)
    p = os.path.join(MD, "osm_base.json")
    if os.path.exists(p) and open(p).read(1) == "{":
        els = json.load(open(p))["elements"]
        def poly(geom): return to_canvas(proj([g["lat"] for g in geom], [g["lon"] for g in geom]), scale0).astype(np.int32)
        for e in els:          # water polygons first
            t = e.get("tags", {})
            if t.get("natural") == "water":
                geoms = [e["geometry"]] if e["type"] == "way" and "geometry" in e else \
                        [m["geometry"] for m in e.get("members", []) if m.get("role") == "outer" and "geometry" in m]
                for g in geoms:
                    if len(g) > 2: cv2.fillPoly(img, [poly(g)], WATER_FILL, cv2.LINE_AA)
        for e in els:
            t = e.get("tags", {})
            if t.get("waterway") == "river" and "geometry" in e:
                cv2.polylines(img, [poly(e["geometry"])], False, WATER_LINE, int(3 * SS), cv2.LINE_AA)
        for cls in ("secondary", "primary", "trunk", "motorway"):
            col, w = ROAD[cls]
            for e in els:
                if e.get("tags", {}).get("highway") == cls and "geometry" in e:
                    cv2.polylines(img, [poly(e["geometry"])], False, col, max(1, int(w * SS)), cv2.LINE_AA)
        # fade the base map out before the edges of the downloaded bbox (data stops there -> hard line)
        (bx0, by0), (bx1, by1) = to_canvas(proj(13.03, 77.25), scale0), to_canvas(proj(12.50, 77.66), scale0)
        ramp = 0.08 * CW
        mx = np.clip(np.minimum(xx - max(bx0, 0), min(bx1, CW) - xx) / ramp, 0, 1)
        my = np.clip(np.minimum(yy - max(by0, 0), min(by1, CH) - yy) / ramp, 0, 1)
        m = (ease(mx) * ease(my))[..., None]
        bg = np.array(BG) * (1 - vig) + np.array(BG2) * vig
        img = (img * m + bg * (1 - m)).astype(np.uint8)
    return img


def offset_right(pts, px):
    """Offset a polyline px to the right of its direction of travel (smoothed normals), so the
    outbound and return legs - which share most of the highway - read as two lanes."""
    d = np.gradient(pts, axis=0)
    k = 15; ker = np.ones(k) / k
    d = np.stack([np.convolve(np.pad(d[:, i], k // 2, mode="edge"), ker, mode="valid") for i in range(2)], 1)
    n = np.stack([-d[:, 1], d[:, 0]], 1); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    return pts + n * px


def polyline_partial(pts, frac):
    """Prefix of a polyline by arc length fraction."""
    if frac <= 0: return pts[:1]
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    L = d[-1] * min(frac, 1)
    k = np.searchsorted(d, L)
    if k >= len(pts): return pts
    a = (L - d[k - 1]) / max(d[k] - d[k - 1], 1e-9)
    return np.vstack([pts[:k], pts[k - 1] + a * (pts[k] - pts[k - 1])])


def pin(img, c, r, col, alpha):
    if alpha <= 0: return
    c = tuple(int(v) for v in c)
    ov = img.copy()
    cv2.circle(ov, c, int(r * 2.2), col, -1, cv2.LINE_AA)
    img[:] = cv2.addWeighted(ov, 0.18 * alpha, img, 1 - 0.18 * alpha, 0)
    cv2.circle(img, c, int(r), col, -1, cv2.LINE_AA)
    cv2.circle(img, c, int(r * 0.42), WHITE, -1, cv2.LINE_AA)


BASE = base_layer()
n_out = r_out; n_back = r_back
leg_idx = np.argmin(np.hypot(*(r_back - proj(*PTS["river"])).T))   # where the return passes the river viewpoint


from PIL import Image, ImageDraw, ImageFont, ImageFilter
FONT = ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", 40, index=2)      # Demi Bold
SAFE = (54, int(0.14 * H), W - 54, int(0.80 * H))                                    # x0, y0, x1, y1
back1, back2 = n_back[:leg_idx + 1], n_back[leg_idx:]                                # temple->river, river->Bengaluru

# timeline (s)
T_BLR_LABEL = (0.05, 0.35); T_OUT = (0.25, 1.45); T_TEMPLE_PIN = 1.40; T_TEMPLE_LABEL = (1.50, 1.80)
T_BACK1 = (1.95, 2.55); T_RIVER_PIN = 2.50; T_RIVER_LABEL = (2.55, 2.85); T_BACK2 = (2.70, 3.45); T_HOME = (3.40, 3.70)


def text_size(txt, track):
    w = sum(FONT.getlength(c) for c in txt) + track * (len(txt) - 1)
    a, d = FONT.getmetrics()
    return w, a + d


def draw_label(pil, txt, anchor, align, alpha, rise=0.0, track=3.5):
    """Tracked uppercase label with soft shadow. anchor=(x,y) = left/right edge (align) at vertical centre."""
    if alpha <= 0.01: return None
    tw, th = text_size(txt, track)
    x = anchor[0] - (tw if align == "right" else 0); y = anchor[1] - th / 2 + 10 * (1 - rise)
    layer = Image.new("RGBA", pil.size, (0, 0, 0, 0)); shadow = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    dl, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    cx = x
    for c in txt:
        ds.text((cx + 2, y + 3), c, font=FONT, fill=(0, 0, 0, int(200 * alpha)))
        dl.text((cx, y), c, font=FONT, fill=(250, 248, 242, int(255 * alpha)))
        cx += FONT.getlength(c) + track
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    pil.alpha_composite(shadow); pil.alpha_composite(layer)
    return (x, y, x + tw, y + th)


def canvas_to_out(pc, z):
    cw, ch = CW / z, CH / z
    return (np.asarray(pc) - np.array([(CW - cw) / 2, (CH - ch) / 2])) * (W / cw)


def frame(t, report=None):
    img = BASE.copy()
    f_out = ease((t - T_OUT[0]) / (T_OUT[1] - T_OUT[0]))
    f_b1 = ease((t - T_BACK1[0]) / (T_BACK1[1] - T_BACK1[0])); f_b2 = ease((t - T_BACK2[0]) / (T_BACK2[1] - T_BACK2[0]))
    over = np.zeros_like(img)
    if f_out > 0:
        cv2.polylines(over, [polyline_partial(offset_right(to_canvas(n_out, scale0), 5 * SS), f_out).astype(np.int32)], False, ROUTE, int(6 * SS), cv2.LINE_AA)
    for part, f in ((back1, f_b1), (back2, f_b2)):
        if f > 0 and len(part) > 1:
            cv2.polylines(over, [polyline_partial(offset_right(to_canvas(part, scale0), 5 * SS), f).astype(np.int32)], False, ROUTE_BACK, int(5 * SS), cv2.LINE_AA)
    glow = cv2.GaussianBlur(over, (0, 0), 9 * SS)
    img = cv2.add(cv2.add(img, (glow * 0.55).astype(np.uint8)), over)
    c_blr, c_tem, c_riv = (to_canvas(proj(*PTS[k]), scale0) for k in ("blr", "temple", "river"))
    home = ease_out((t - T_HOME[0]) / (T_HOME[1] - T_HOME[0]))
    pin(img, c_blr, 11 * SS * (1 + 0.25 * np.sin(np.pi * home)), WHITE, 1.0 if t > 0.05 else 0)   # pulse on return
    pt = ease_out((t - T_TEMPLE_PIN) / 0.30)
    pin(img, c_tem, 15 * SS * (0.6 + 0.4 * pt + 0.12 * np.sin(np.pi * pt)), PIN, pt)
    pr = ease_out((t - T_RIVER_PIN) / 0.30)
    pin(img, c_riv, 13 * SS * (0.6 + 0.4 * pr + 0.12 * np.sin(np.pi * pr)), ROUTE_BACK, pr)
    # camera: gentle eased push-in (no upscale beyond the 3x canvas)
    z = 1.0 + 0.10 * ease(t / DUR)
    cw, ch = CW / z, CH / z
    x0, y0 = int((CW - cw) / 2), int((CH - ch) / 2)
    out = cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (W, H), interpolation=cv2.INTER_AREA)
    # labels at output resolution (crisp), attached to the pins through the camera transform
    pil = Image.fromarray(out[..., ::-1]).convert("RGBA")
    pb, ptm, prv = (canvas_to_out(c, z) for c in (c_blr, c_tem, c_riv))
    a_b = ease((t - T_BLR_LABEL[0]) / (T_BLR_LABEL[1] - T_BLR_LABEL[0]))
    boxes = {}
    # above-left of the pin: the route leaves the pin heading left, so a level label touched it (v5 check)
    boxes["blr"] = draw_label(pil, "BENGALURU", (pb[0] - 30, pb[1] - 40), "right", a_b * (1 - home), rise=a_b)
    boxes["home"] = draw_label(pil, "BACK TO BENGALURU", (pb[0] - 30, pb[1] - 40), "right", home, rise=home)
    a_t = ease((t - T_TEMPLE_LABEL[0]) / (T_TEMPLE_LABEL[1] - T_TEMPLE_LABEL[0]))
    boxes["temple"] = draw_label(pil, "SIDDAPPAJI TEMPLE", (ptm[0] - 22, ptm[1] + 58), "left", a_t, rise=a_t)
    a_r = ease((t - T_RIVER_LABEL[0]) / (T_RIVER_LABEL[1] - T_RIVER_LABEL[0]))
    # below-right of the pin: the return route runs NE through the area above-right (overlapped in v5 check)
    boxes["river"] = draw_label(pil, "RIVER CROSSING", (prv[0] + 30, prv[1] + 50), "left", a_r, rise=a_r)
    if report is not None:
        for k, bx in boxes.items():
            if bx: report[k] = bx
    return np.asarray(pil.convert("RGB"))[..., ::-1].copy()


def safe_area_check():
    rep = {}
    for t in np.arange(0, DUR, 0.1): frame(t, rep)
    bad = {k: [round(v) for v in b] for k, b in rep.items()
           if b[0] < SAFE[0] or b[1] < SAFE[1] or b[2] > SAFE[2] or b[3] > SAFE[3]}
    print("label boxes (x0,y0,x1,y1):", {k: [round(v) for v in b] for k, b in rep.items()})
    print("safe area", SAFE, "->", "ALL INSIDE" if not bad else f"OUTSIDE: {bad}")


if "--check" in sys.argv:
    safe_area_check(); sys.exit()


if "--still" in sys.argv:
    t = float(sys.argv[sys.argv.index("--still") + 1]); out = sys.argv[sys.argv.index("--still") + 2]
    cv2.imwrite(out, frame(t), [cv2.IMWRITE_JPEG_QUALITY, 92]); print(out); sys.exit()

os.makedirs(os.path.join(ROOT, "work", "shots"), exist_ok=True)
dst = os.path.join(ROOT, "work", "shots", "M01.mov")
p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-vf", "setparams=range=pc:color_primaries=bt709:color_trc=bt709:colorspace=gbr,"
                             "zscale=range=limited:matrix=709:primaries=709:transfer=709,format=yuv422p10le",
                      "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le",
                      "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", dst],
                     stdin=subprocess.PIPE)
for i in range(int(DUR * FPS)):
    p.stdin.write(frame(i / FPS).tobytes())
p.stdin.close(); p.wait()
print("M01", dst, int(DUR * FPS), "frames")
