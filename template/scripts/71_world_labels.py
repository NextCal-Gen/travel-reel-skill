"""World-locked labels for 360 shots: a pin + label fixed to a real direction in the scene, so it stays on
the temple / the hill / the bridge while the virtual camera pans past it. No tracking: every 360 shot's
camera path is known exactly (EDL keyframes [t, yaw, pitch, h_fov] -> v360 flat, reset_rot=1), so each
frame's screen position is pure projection maths (verified against v360 output to < 2 px).

Run after `source scripts/env.sh`, once work/shots/<id>.mov exist:
  71_world_labels.py still <shot> <t>          -> assets/world/<shot>_<t>.jpg: the rendered frame with a
                                                 100 px grid. View it and read the pixel of the target.
  71_world_labels.py locate <shot> <t> <x> <y> -> world direction (yaw, pitch) of that pixel at that moment
  71_world_labels.py render [--plan assets/world_labels.json]
      plan = [{"id": "lbl_bana", "shot": "S04", "yaw": 41.2, "pitch": 6.5, "text": "Ba Na Hills",
               "sub": "", "t0": 0.4, "t1": 2.8, "side": "above", "color": "#FFF8EE", "accent": "#F2C14E"}]
      -> work/motion/<id>.mov (transparent ProRes 4444, same convention as 70_motion) + <id>.json report,
         and an entry {"id", "start": shot start in the reel} upserted into assets/motion_plan.json,
         so `70_motion.py composite` lays it on like any other graphic.
Labels fade in/out over 0.3 s, fade out before any part leaves the Instagram safe zone, and disappear
when the target turns behind the camera. Text only (no emoji): one short name, in the CLAUDE.md language."""
import csv, json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_edl import load_edl, interp
from lib_safe import W, H, SAFE, violations

FPS = 30
SKILL = os.environ.get("TRAVEL_REEL_SKILL", os.path.expanduser("~/.claude/skills/travel-reel"))
FONT_DIR = os.path.join(SKILL, "template", "motion", "assets", "fonts")
WORK = os.path.join(ROOT, "work", "motion")


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


# ---------------------------------------------------------------- projection (matches ffmpeg v360 flat, reset_rot=1)
def _Ry(a):
    return np.array([[math.cos(a), 0, -math.sin(a)], [0, 1, 0], [math.sin(a), 0, math.cos(a)]])


def _Rx(a):
    return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])


def project(yaw_w, pitch_w, yaw, pitch, hfov):
    """World direction (deg) -> (x, y, depth) in the 1080x1920 rendered frame for a camera (deg)."""
    lo, la = math.radians(yaw_w), math.radians(pitch_w)
    v = np.array([math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo)])
    c = _Rx(math.radians(pitch)) @ _Ry(math.radians(yaw)) @ v
    f = (W / 2) / math.tan(math.radians(hfov / 2))
    if c[2] <= 1e-6:
        return None, None, c[2]
    return W / 2 + f * c[0] / c[2], H / 2 - f * c[1] / c[2], c[2]


def unproject(x, y, yaw, pitch, hfov):
    f = (W / 2) / math.tan(math.radians(hfov / 2))
    c = np.array([(x - W / 2) / f, -(y - H / 2) / f, 1.0])
    v = _Ry(math.radians(yaw)).T @ _Rx(math.radians(pitch)).T @ c
    v /= np.linalg.norm(v)
    return math.degrees(math.atan2(v[0], v[2])), math.degrees(math.asin(v[1]))


def shot_table():
    shots, start = {}, 0
    for s in load_edl():
        p = os.path.join(ROOT, "work", "shots", f"{s['id']}.mov")
        n = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                                "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip() or 0) \
            if os.path.exists(p) else int(round(s["dur"] * FPS))
        s["frames"], s["start_frame"] = n, start
        start += n
        shots[s["id"]] = s
    return shots


def camera(s, t):
    yaw, pitch, hf = interp(s["kf"], t)
    return yaw, pitch, hf


def need360(s):
    if len(s["kf"][0]) != 4 or s.get("kind", "360") == "flat":
        sys.exit(f"{s['id']} is not a 360 shot (world labels need yaw/pitch keyframes)")


# ---------------------------------------------------------------- still / locate
def cmd_still():
    sid, t = sys.argv[2], float(sys.argv[3])
    p = os.path.join(ROOT, "work", "shots", f"{sid}.mov")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", p, "-frames:v", "1", "-vf",
                          "scale=in_color_matrix=bt709:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    im = Image.frombytes("RGB", (W, H), raw)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 100):
        d.line([(x, 0), (x, H)], fill=(255, 255, 0) if x % 500 == 0 else (255, 255, 255), width=1)
        d.text((x + 4, 4), str(x), fill=(255, 255, 0))
    for y in range(0, H, 100):
        d.line([(0, y), (W, y)], fill=(255, 255, 0) if y % 500 == 0 else (255, 255, 255), width=1)
        d.text((4, y + 4), str(y), fill=(255, 255, 0))
    out = os.path.join(ROOT, "assets", "world", f"{sid}_{t:.2f}.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, quality=88)
    print(out)


def cmd_locate():
    sid, t, x, y = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    s = shot_table()[sid]; need360(s)
    yw, pw = unproject(x, y, *camera(s, t))
    print(json.dumps(dict(shot=sid, t=t, x=x, y=y, yaw=round(yw, 2), pitch=round(pw, 2))))


# ---------------------------------------------------------------- render
def sprite(text, sub, side, color, accent):
    """Label sprite: pin dot + leader + text, anchored at the dot. Returns (RGBA image, anchor x, anchor y)."""
    fb = ImageFont.truetype(os.path.join(FONT_DIR, "BeVietnamPro-Bold.ttf"), 44)
    fs = ImageFont.truetype(os.path.join(FONT_DIR, "BeVietnamPro-SemiBold.ttf"), 28)
    tw = int(fb.getlength(text)); sw = int(fs.getlength(sub)) if sub else 0
    w = max(tw, sw) + 40; th = 54 + (36 if sub else 0); lead = 70; pad = 20
    hgt = th + lead + 40
    im = Image.new("RGBA", (w + 2 * pad, hgt + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = im.width // 2
    up = side != "below"
    ay = (im.height - pad - 16) if up else (pad + 16)                 # anchor (dot centre)
    ty = (ay - 16 - lead - th) if up else (ay + 16 + lead)
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    for dd, fill in ((sd, (0, 0, 0, 150)), (d, None)):
        col = fill or color
        dd.line([(cx, ay - (14 if up else -14)), (cx, ty + (th if up else 0))], fill=fill or accent, width=4)
        dd.ellipse([cx - 13, ay - 13, cx + 13, ay + 13], outline=fill or accent, width=5)
        dd.ellipse([cx - 5, ay - 5, cx + 5, ay + 5], fill=fill or accent)
        dd.text((cx - tw / 2, ty), text, font=fb, fill=col)
        if sub:
            dd.text((cx - sw / 2, ty + 54), sub, font=fs, fill=col)
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    out = Image.alpha_composite(shadow, im)
    return out, cx, ay


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def render_label(L, shots):
    s = shots[L["shot"]]; need360(s)
    spr, ax, ay = sprite(L["text"], L.get("sub", ""), L.get("side", "above"),
                         L.get("color", "#FFF8EE"), L.get("accent", "#F2C14E"))
    sw_, sh_ = spr.size
    n = s["frames"]; t0 = float(L.get("t0", 0)); t1 = float(L.get("t1", n / FPS)); fade = 0.3; margin = 60.0
    out = os.path.join(WORK, L["id"] + ".mov"); os.makedirs(WORK, exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-vf",
                            "scale=out_color_matrix=bt601:out_range=tv,format=yuva444p10le",   # 70_motion convention
                            "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", out], stdin=subprocess.PIPE)
    bad, path = [], []
    for i in range(n):
        t = i / FPS
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x, y, depth = project(float(L["yaw"]), float(L["pitch"]), *camera(s, t))
        a = smooth((t - t0) / fade) * smooth((t1 - t) / fade)
        if x is not None and a > 0:
            bx0, by0 = x - ax, y - ay
            # fade before any part leaves the safe zone (incl. the button column) or the target nears the edge
            right = SAFE["btn_right"] if by0 + sh_ > SAFE["btn_top"] else SAFE["right"]
            inside = min(bx0 - SAFE["left"], right - (bx0 + sw_), by0 - SAFE["top"], SAFE["bottom"] - (by0 + sh_))
            a *= smooth(inside / margin) * smooth((depth - 0.15) / 0.2)
            if a > 0.002:
                fx, fy = math.floor(bx0), math.floor(by0)
                sub = spr.transform(spr.size, Image.AFFINE, (1, 0, fx - bx0, 0, 1, fy - by0), resample=Image.BILINEAR)
                if a < 0.999:
                    alpha = sub.getchannel("A").point(lambda v, a=a: int(v * a))
                    sub.putalpha(alpha)
                frame.alpha_composite(sub, (int(fx), int(fy))) if 0 <= fx and 0 <= fy and fx + sw_ <= W and fy + sh_ <= H \
                    else frame.paste(sub, (int(fx), int(fy)), sub)
            path.append(dict(t=round(t, 3), x=round(x, 1), y=round(y, 1), alpha=round(a, 3)))
        al = np.asarray(frame.getchannel("A"))
        v = violations(al)
        if v:
            bad.append(dict(frame=i, **v))
        enc.stdin.write(frame.tobytes())
    enc.stdin.close(); enc.wait()
    vis = [p for p in path if p["alpha"] > 0.5]
    rep = dict(template="world_label", name=L["id"], vars=L, frames=n, safe_zone_ok=not bad, safe_zone_violations=bad[:5],
               visible_s=round(len(vis) / FPS, 2), start=round(s["start_frame"] / FPS, 3))
    json.dump(rep, open(os.path.join(WORK, L["id"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if len(vis) < FPS:
        print(f"warning: {L['id']} is readable for only {len(vis) / FPS:.1f} s (target off screen, outside the safe zone, "
              f"or t0-t1 too short): pick another direction or time window")
    return rep


def cmd_render():
    plan_p = os.path.join(ROOT, arg("--plan", "assets/world_labels.json"))
    labels = json.load(open(plan_p, encoding="utf-8"))
    shots = shot_table()
    mp = os.path.join(ROOT, "assets", "motion_plan.json")
    plan = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else []
    ok = True
    for L in labels:
        rep = render_label(L, shots)
        ok &= rep["safe_zone_ok"]
        plan = [p for p in plan if p["id"] != L["id"]] + [dict(id=L["id"], start=rep["start"])]
        print(json.dumps({k: rep[k] for k in ("name", "start", "visible_s", "safe_zone_ok")}))
    json.dump(sorted(plan, key=lambda p: p["start"]), open(mp, "w", encoding="utf-8"), indent=1)
    print("motion plan updated:", os.path.relpath(mp, ROOT), "-> run 70_motion.py composite")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    {"still": cmd_still, "locate": cmd_locate, "render": cmd_render}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
