"""Phase 8 module: motion-graphic overlays (HyperFrames HTML/GSAP -> transparent ProRes 4444),
composited onto the graded timeline. Graphics never pass through the grade or the LUTs.

Run after `source scripts/env.sh`:
  70_motion.py list
      templates, durations and their variables
  70_motion.py map --country Vietnam --stops "Bengaluru:12.97,77.59;Hanoi:21.03,105.85;Hoi An:15.88,108.33:days 6-8@bike"
                  [--traveller plane|bike|car|none] [--merge-px 30] [--out assets/motion/map.json]
      country outline (Natural Earth, the country's own point-of-view borders where published) + stops,
      projected into the hop_map box. The output JSON is a --vars file for hop_map.
  70_motion.py render <template> [--name ID] [--vars file.json] [--set key=value ...] [--bg-time T] [--allow-outside]
                    [--no-auto-colors] [--stutter 12]
      lint -> render work/motion/ID.mov -> checks (alpha, frame count, safe zone) -> assets/motion/ID_sheet.jpg
      (frames composited over the timeline at T when --bg-time is given, else over a neutral gradient). VIEW the sheet.
      --stutter 12: the graphic steps at 12 fps inside the 30 fps reel (hand-built infographic look; footage stays smooth).
      Auto colours (with --bg-time, for templates with a `color` variable the user did not set): the text colour's
      worst-case contrast is measured against the footage under the rendered graphic; below 4.5:1 it is replaced
      by lib_text's pick from those pixels (+ its accent, shadow off for dark text) and the graphic re-rendered.
  70_motion.py composite [--plan assets/motion_plan.json] [--base FILE] [--out work/timeline_motion.mov] [--preview VER]
      plan = [{"id": "title", "start": 0.4}, ...]; base defaults to work/timeline_text.mov, else timeline_prores.mov.
      --preview VER also writes the muted review preview previews/rough_cut_vVER.mp4 from the result.

Templates: the skill's template/motion/templates/*.html; a project copy in motion/templates/ overrides one.
Toolkit: $TRAVEL_REEL_TOOLKIT/motion (pinned hyperframes + gsap; bootstrap.sh --create --with-motion).
Verified pitfalls (see SKILL.md): HyperFrames ProRes is BT.601 limited range and untagged, so it is converted
to BT.709 before overlaying; templates never measure text (fonts may not be ready), they use fixed boxes."""
import glob, json, math, os, re, shutil, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
ROOT = os.environ.get("PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from lib_safe import W, H, SAFE, violations  # noqa: E402

TK = os.environ.get("TRAVEL_REEL_TOOLKIT", os.path.expanduser("~/travel-reel-toolkit"))
SKILL = os.environ.get("TRAVEL_REEL_SKILL", os.path.expanduser("~/.claude/skills/travel-reel"))
MOTION_TK = os.path.join(TK, "motion")
HF = os.path.join(MOTION_TK, "node_modules", ".bin", "hyperframes")
GSAP = os.path.join(MOTION_TK, "node_modules", "gsap", "dist", "gsap.min.js")
SRC = os.path.join(SKILL, "template", "motion")
WORK = os.path.join(ROOT, "work", "motion")
ASSETS = os.path.join(ROOT, "assets", "motion")
FPS = 30
ENC = ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le",
       "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
       "-an", "-map_metadata", "-1"]
NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
NE_POV = {"arg", "bdg", "bra", "chn", "deu", "egy", "esp", "fra", "gbr", "grc", "idn", "ind", "iso", "isr", "ita",
          "jpn", "kor", "mar", "nep", "nld", "pak", "pol", "prt", "pse", "rus", "sau", "swe", "tlc", "tur", "twn",
          "ukr", "usa", "vnm"}


CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def node22():
    """A Node >= 22 binary: PATH first, then nvm installs (newest first), then Homebrew. nvm users often have an
    older default node first on PATH, and the hyperframes launcher runs whatever `node` PATH gives it."""
    def major(p):
        try:
            return int(subprocess.run([p, "-p", "process.versions.node.split('.')[0]"], capture_output=True,
                                      text=True, timeout=10).stdout.strip() or 0)
        except Exception:
            return 0
    nvm = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/v*/bin/node")),
                 key=lambda p: [int(x) for x in re.findall(r"v(\d+)\.(\d+)\.(\d+)", p)[0]], reverse=True)
    for c in [shutil.which("node")] + nvm + ["/opt/homebrew/opt/node/bin/node", "/opt/homebrew/bin/node", "/usr/local/bin/node"]:
        if c and os.path.exists(c) and major(c) >= 22:
            return c
    return None


def hf_env():
    e = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1")
    n = node22()
    if not n:
        sys.exit("Node 22+ not found (PATH, nvm, Homebrew): ~/.claude/skills/travel-reel/bootstrap.sh --install-system --with-motion")
    e["PATH"] = os.path.dirname(n) + os.pathsep + e.get("PATH", "")
    browser = os.environ.get("MOTION_BROWSER") or (CHROME_APP if os.path.exists(CHROME_APP) else "")
    if browser:                                                  # else HyperFrames uses the Chrome it downloaded
        e["HYPERFRAMES_BROWSER_PATH"] = browser
    return e


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def template_path(name):
    for d in (os.path.join(ROOT, "motion", "templates"), os.path.join(SRC, "templates")):
        p = os.path.join(d, name + ".html")
        if os.path.exists(p):
            return p
    sys.exit(f"no template '{name}' (see: 70_motion.py list)")


def template_meta(path):
    s = open(path, encoding="utf-8").read()
    m = re.search(r"data-composition-variables='(.*?)'>", s, re.S)
    dur = float(re.search(r'data-duration="([\d.]+)"', s).group(1))
    return (json.loads(m.group(1)) if m else []), dur


# ---------------------------------------------------------------- list
def cmd_list():
    names = set()
    for d in (os.path.join(SRC, "templates"), os.path.join(ROOT, "motion", "templates")):
        if os.path.isdir(d):
            names |= {f[:-5] for f in os.listdir(d) if f.endswith(".html")}
    for n in sorted(names):
        decl, dur = template_meta(template_path(n))
        print(f"\n{n}  ({dur:g} s)")
        for v in decl:
            d = v.get("default")
            d = d if len(str(d)) < 70 else str(d)[:67] + "..."
            print(f"  {v['id']:<13} {v.get('label', '')}   default: {d}")


# ---------------------------------------------------------------- map
def ne_file(country):
    """Natural Earth countries file: the country's own point-of-view (10m) file when published, else 50m."""
    import urllib.request
    cache = os.path.join(TK, "cache", "naturalearth"); os.makedirs(cache, exist_ok=True)

    def get(fname):
        p = os.path.join(cache, fname)
        if not os.path.exists(p):
            print(f"downloading {fname} (Natural Earth, public domain)")
            urllib.request.urlretrieve(NE_BASE + fname, p + ".part"); os.replace(p + ".part", p)
        return p
    base = json.load(open(get("ne_50m_admin_0_countries.geojson"), encoding="utf-8"))
    feat = find_country(base, country)
    iso = (feat["properties"].get("ADM0_A3") or feat["properties"].get("ISO_A3") or "").lower()
    if iso in NE_POV:
        pov = json.load(open(get(f"ne_10m_admin_0_countries_{iso}.geojson"), encoding="utf-8"))
        f2 = find_country(pov, country, required=False)
        if f2:
            return f2, f"ne_10m_admin_0_countries_{iso} ({iso.upper()} point of view)"
    return feat, "ne_50m_admin_0_countries (default point of view)"


def find_country(fc, q, required=True):
    q = q.strip().lower()
    keys = ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "FORMAL_EN", "ISO_A3", "ADM0_A3", "SOVEREIGNT")
    for f in fc["features"]:
        pr = f["properties"]
        if any(str(pr.get(k, "")).strip().lower() == q for k in keys):
            return f
    if required:
        sys.exit(f"country '{q}' not found in Natural Earth (try the English name or ISO3 code)")
    return None


def cmd_map():
    """Stops: "Label:lat,lon[:sub][@mode];..." in travel order (mode = plane | bike | car | none for the leg
    arriving at that stop). Stops outside the country are drawn at its border ("from Bengaluru"); a trip that
    leaves and returns to the same place abroad gets one "⇄" marker. Stops closer than --merge-px on the map
    become one place ("Da Nang · Hoi An"). Traveller icon per leg: the stop's @mode, else --traveller, else
    plane for an international trip (any stop abroad) and bike for a domestic one."""
    import cv2
    country = arg("--country") or sys.exit("--country required")
    merge_px = float(arg("--merge-px", 30))
    stops = []
    for part in (arg("--stops", "") or "").split(";"):
        if not part.strip():
            continue
        part, _, mode = part.partition("@")
        bits = part.split(":")
        lat, lon = (float(x) for x in bits[1].split(","))
        stops.append(dict(label=bits[0].strip(), lat=lat, lon=lon, sub=":".join(bits[2:]).strip(), mode=mode.strip().lower()))
    if len(stops) < 1:
        sys.exit("--stops required")
    feat, src = ne_file(country)
    g = feat["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    rings = [np.array(p[0], dtype=np.float64) for p in polys]                   # exterior rings only
    lat0 = math.radians(np.mean(np.concatenate(rings)[:, 1]))
    proj = lambda lon, lat: np.stack([np.asarray(lon) * math.cos(lat0), -np.asarray(lat)], axis=-1)
    P = [proj(r[:, 0], r[:, 1]) for r in rings]
    area = [abs(cv2.contourArea(p.astype(np.float32))) for p in P]
    big = max(area)
    sp = [proj(s["lon"], s["lat"]) for s in stops]
    # inside the country? (point in any ring, with a small tolerance for coastal cities)
    for s, q in zip(stops, sp):
        s["abroad"] = all(cv2.pointPolygonTest(p.astype(np.float32).reshape(-1, 1, 2), (float(q[0]), float(q[1])), True) < -0.15
                          for p in P)
    home = [q for s, q in zip(stops, sp) if not s["abroad"]] or sp
    keep = []
    for p, a in zip(P, area):                                                     # drop specks, keep islands near stops
        near = any(np.min(np.hypot(*(p - q).T)) < 0.3 for q in home)
        if a >= big * 0.004 or near:
            keep.append(p)
    pts = np.concatenate(keep + [np.array(home)])
    lo, hi = pts.min(0), pts.max(0)
    # hop_map shows box x 150-850 / y 40-960 (window x 110-890 of the 1000 box); 60 px margin for border markers
    bw, bh, mg = 700.0, 920.0, 60.0
    sc = min((bw - 2 * mg) / max(hi[0] - lo[0], 1e-9), (bh - 2 * mg) / max(hi[1] - lo[1], 1e-9))
    ox = 150 + (bw - (hi[0] - lo[0]) * sc) / 2 - lo[0] * sc
    oy = 40 + (bh - (hi[1] - lo[1]) * sc) / 2 - lo[1] * sc
    tf = lambda p: np.stack([p[..., 0] * sc + ox, p[..., 1] * sc + oy], axis=-1)
    d = []
    for p in keep:
        q = tf(p).astype(np.float32).reshape(-1, 1, 2)
        q = cv2.approxPolyDP(q, 1.1, True).reshape(-1, 2)
        if len(q) >= 3:
            d.append("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in q) + " Z")
    # positions: places abroad go to the edge of the drawing, in their real direction from the country's centre
    cx, cy = 150 + bw / 2, 40 + bh / 2
    for s, q in zip(stops, sp):
        x, y = (float(v) for v in tf(np.array(q)))
        if s["abroad"]:
            dx, dy = x - cx, y - cy
            k = min((bw / 2 - 25) / max(abs(dx), 1e-9), (bh / 2 - 25) / max(abs(dy), 1e-9))
            x, y = cx + dx * k, cy + dy * k
        s["x"], s["y"] = x, y
    # merge nearby places into one node (same place visited again, or two places a few km apart)
    nodes, route = [], []
    for s in stops:
        j = next((i for i, n in enumerate(nodes) if n["abroad"] == s["abroad"] and
                  (n["labels"][0] == s["label"] or math.hypot(n["x"] - s["x"], n["y"] - s["y"]) < merge_px)), None)
        if j is None:
            nodes.append(dict(labels=[s["label"]], subs=[s["sub"]] if s["sub"] else [], x=s["x"], y=s["y"], abroad=s["abroad"]))
            j = len(nodes) - 1
        else:
            n = nodes[j]
            if s["label"] not in n["labels"]:
                n["labels"].append(s["label"])
            if s["sub"] and s["sub"] not in n["subs"]:
                n["subs"].append(s["sub"])
        if not route or route[-1] != j:
            route.append(j)
    international = any(s["abroad"] for s in stops)
    default = arg("--traveller") or ("plane" if international else "bike")
    if default not in ("plane", "bike", "car", "none"):
        sys.exit("--traveller must be plane, bike, car or none")
    # mode of each leg = the @mode of the first stop that leg arrives at
    legs, seq = [], []
    for s in stops:                                                                # rebuild leg modes on the merged route
        j = next(i for i, n in enumerate(nodes) if s["label"] in n["labels"])
        if not seq or seq[-1][0] != j:
            seq.append((j, s["mode"]))
    legs = [(m or default) for _, m in seq[1:]]
    # merged places: the first name is the label, the others go on the small line under it
    out_stops = [dict(label=n["labels"][0], x=round(n["x"], 1), y=round(n["y"], 1),
                      **({"sub": " · ".join(n["labels"][1:] + n["subs"])} if (n["labels"][1:] or n["subs"]) else {}),
                      **({"edge": True} if n["abroad"] else {}))
                 for n in nodes]
    res = dict(outline=" ".join(d), stops=json.dumps(out_stops, ensure_ascii=False), route=json.dumps(route),
               legs=json.dumps(legs))
    out = arg("--out", os.path.join(ASSETS, "map.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{out}: {len(d)} polygons, {sum(s.count('L') for s in d)} points; borders from {src}")
    print(f"places: {[n['labels'] for n in nodes]}  route: {route}  legs: {legs}  "
          f"({'international' if international else 'domestic'} trip, default traveller {default})")
    print("Use: 70_motion.py render hop_map --vars", os.path.relpath(out, ROOT), "--set title=...")


# ---------------------------------------------------------------- render + checks
def build_dir(template, name):
    b = os.path.join(WORK, "build", name)
    shutil.rmtree(b, ignore_errors=True); os.makedirs(b)
    shutil.copytree(os.path.join(SRC, "assets"), os.path.join(b, "assets"))
    proj_assets = os.path.join(ROOT, "motion", "assets")
    if os.path.isdir(proj_assets):                                               # project extras (images, fonts)
        shutil.copytree(proj_assets, os.path.join(b, "assets"), dirs_exist_ok=True)
    shutil.copy(os.path.join(SRC, "hyperframes.json"), b)
    os.makedirs(os.path.join(b, "assets", "vendor"), exist_ok=True)
    shutil.copy(GSAP, os.path.join(b, "assets", "vendor", "gsap.min.js"))
    shutil.copy(template_path(template), os.path.join(b, "index.html"))
    return b


def alpha_frames(path, every=1):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"select=not(mod(n\\,{every})),alphaextract,format=gray",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W)
    p.wait()


def rgba_at(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf",
                          "scale=in_color_matrix=bt601:in_range=tv,format=rgba", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 4).astype(np.float32) / 255


def background(t):
    base = base_timeline()
    if t is not None and base:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", base, "-frames:v", "1", "-vf",
                              "scale=in_color_matrix=bt709:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255
    y = np.linspace(0, 1, H)[:, None, None]
    return np.broadcast_to(np.array([0.45, 0.55, 0.62]) * (1 - y) + np.array([0.30, 0.34, 0.28]) * y, (H, W, 3)).copy()


def sheet(name, times, bg_t=None):
    import cv2
    mov = os.path.join(WORK, name + ".mov")
    tiles = []
    for k, t in enumerate(times):
        a = rgba_at(mov, t)
        bg = background(None if bg_t is None else bg_t + t)
        c = (bg * (1 - a[..., 3:]) + a[..., :3] * a[..., 3:]) * 255
        c = cv2.cvtColor(c.astype(np.uint8), cv2.COLOR_RGB2BGR)
        x0, y0, x1, y1 = SAFE["left"], SAFE["top"], SAFE["right"], SAFE["bottom"]
        cv2.rectangle(c, (x0, y0), (x1, y1), (60, 60, 230), 2)
        cv2.line(c, (SAFE["btn_right"], SAFE["btn_top"]), (SAFE["btn_right"], y1), (60, 60, 230), 2)
        cv2.putText(c, f"t={t:.2f}s", (24, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 255, 255), 3)
        tiles.append(cv2.resize(c, (W // 3, H // 3), interpolation=cv2.INTER_AREA))
    os.makedirs(ASSETS, exist_ok=True)
    out = os.path.join(ASSETS, f"{name}_sheet.jpg")
    cv2.imwrite(out, np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


def cmd_render():
    template = sys.argv[2]
    name = arg("--name", template)
    for p, what in ((HF, "hyperframes"), (GSAP, "gsap")):
        if not os.path.exists(p):
            sys.exit(f"{what} missing in {MOTION_TK}: run ~/.claude/skills/travel-reel/bootstrap.sh --create --with-motion")
    decl, dur = template_meta(template_path(template))
    known = {v["id"] for v in decl}
    vals = {}
    if arg("--vars"):
        vals.update(json.load(open(os.path.join(ROOT, arg("--vars")) if not os.path.isabs(arg("--vars")) else arg("--vars"), encoding="utf-8")))
    for i, a in enumerate(sys.argv):
        if a == "--set":
            k, _, v = sys.argv[i + 1].partition("=")
            vals[k] = v
    unknown = set(vals) - known
    if unknown:
        sys.exit(f"unknown variables for {template}: {sorted(unknown)} (known: {sorted(known)})")
    for v in decl:                                                               # numbers stay numbers
        if v.get("type") == "number" and v["id"] in vals:
            vals[v["id"]] = float(vals[v["id"]])
    out = render_once(template, name, vals)
    bg_t = float(arg("--bg-time")) if arg("--bg-time") else None
    auto = None
    if bg_t is not None and "--no-auto-colors" not in sys.argv and "color" in known and "color" not in vals \
            and "theme" not in vals:                               # a colour or theme the user chose is kept
        auto = auto_colors(out, decl, vals, dur, bg_t, template)
        if auto.get("changed"):
            vals.update(auto["set"]); out = render_once(template, name, vals)
    if arg("--stutter"):                                    # Vox-style stepped motion: hold each pose for 30/N frames
        n = float(arg("--stutter"))
        tmp = out + ".stutter.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf", f"fps={n:g},fps={FPS}", "-c:v", "prores_ks",
                        "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", "-an", out_tmp := tmp],
                       check=True)
        os.replace(out_tmp, out)
    # checks
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                    "stream=pix_fmt,width,height,nb_read_frames", "-of", "json", out],
                                   capture_output=True, text=True).stdout)["streams"][0]
    want = round(dur * FPS)
    rep = dict(template=template, name=name, vars=vals, pix_fmt=pr["pix_fmt"], frames=int(pr["nb_read_frames"]),
               frames_expected=want, size=f"{pr['width']}x{pr['height']}")
    rep["alpha_ok"] = "a" in pr["pix_fmt"].replace("yuv", "")
    if auto:
        rep["auto_colors"] = {k: v for k, v in auto.items() if k != "set"}
    rep["frames_ok"] = abs(rep["frames"] - want) <= 1
    bad = []
    for i, a in enumerate(alpha_frames(out, every=2)):
        v = violations(a)
        if v:
            bad.append(dict(frame=i * 2, **v))
    rep["safe_zone_ok"] = not bad
    rep["safe_zone_violations"] = bad[:5]
    times = [round(dur * f, 2) for f in (0.15, 0.35, 0.6, 0.85)]
    rep["sheet"] = sheet(name, times, bg_t)
    json.dump(rep, open(os.path.join(WORK, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "vars"}, indent=1, ensure_ascii=False))
    ok = rep["alpha_ok"] and rep["frames_ok"] and (rep["safe_zone_ok"] or "--allow-outside" in sys.argv)
    sys.exit(0 if ok else 1)


def render_once(template, name, vals):
    b = build_dir(template, name)
    os.makedirs(WORK, exist_ok=True)
    vf = os.path.join(b, "vars.json"); json.dump(vals, open(vf, "w", encoding="utf-8"), ensure_ascii=False)
    lint = subprocess.run([HF, "lint", b], capture_output=True, text=True, env=hf_env())
    errs = re.search(r"(\d+) error", lint.stdout + lint.stderr)
    if lint.returncode != 0 or (errs and int(errs.group(1)) > 0):
        print(lint.stdout[-3000:], lint.stderr[-2000:]); sys.exit("lint failed")
    out = os.path.join(WORK, name + ".mov")
    r = subprocess.run([HF, "render", b, "--format", "mov", "-o", out, "--quiet", "--strict", "--variables-file", vf],
                       capture_output=True, text=True, env=hf_env())
    if r.returncode != 0 or not os.path.exists(out):
        print(r.stdout[-4000:], r.stderr[-3000:]); sys.exit("render failed")
    return out


AUTO_ACCENT = ("title_reveal", "day_counter", "hop_map")       # accent drawn on the footage; elsewhere it is a fill behind text


def auto_colors(mov, decl, vals, dur, bg_t, template="", thr=4.5):
    """Worst-case contrast of the template's text colour against the footage under the rendered graphic
    (union of solid alpha, dilated), at 3 moments; if below thr, pick lib_text's colour from those pixels."""
    import cv2
    import lib_text as T
    defaults = {v["id"]: v.get("default") for v in decl}
    mask = np.zeros((H, W), bool)
    for a in alpha_frames(mov, every=3):
        mask |= a > 160
    if not mask.any():
        return dict(changed=False, note="nothing opaque to measure")
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    bg = np.concatenate([background(bg_t + dur * f)[mask] for f in (0.3, 0.6, 0.85)]).astype(np.float64)
    L = T.rel_lum(bg); lo, hi = float(np.percentile(L, 5)), float(np.percentile(L, 95))

    def worst(rgb):
        lt = float(T.rel_lum(np.asarray(rgb)))
        return T.contrast(lt, hi) if lt > np.median(L) else T.contrast(lt, lo)
    hexrgb = lambda h: np.array([int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    tohex = lambda c: "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in c)
    cur = str(vals.get("color") or defaults.get("color") or ("#1E1712" if vals.get("theme") == "dark" else "#FFFFFF"))
    before = round(worst(hexrgb(cur)), 2)
    if before >= thr:
        return dict(changed=False, color=cur, contrast=before)
    cands, accent, _ = T.local_colors(bg.astype(np.float32))
    scored = [(k, c, worst(c)) for k, c in cands]                  # lib_text's harmony order
    passing = [x for x in scored if x[2] >= thr]
    best = passing[0] if passing else max(scored, key=lambda x: x[2])
    if not passing and best[2] <= before:                       # busy background: no colour wins, keep the original
        return dict(changed=False, color=cur, contrast=before,
                    note=f"no colour reaches {thr}:1 on this background (light and dark under the text); "
                         "the text shadow carries it: check the sheet, or place the graphic over a calmer area")
    new = {"color": tohex(best[1])}
    ids = {v["id"] for v in decl}
    if "accent" in ids and "accent" not in vals and accent is not None and template.startswith(AUTO_ACCENT):
        new["accent"] = tohex(accent)
    if "shadow" in ids and "shadow" not in vals and float(T.rel_lum(best[1])) < 0.3:
        new["shadow"] = 0.0                                     # dark text: no dark drop shadow
    return dict(changed=True, set=new, kind=best[0], color_before=cur, contrast_before=before,
                color=new["color"], contrast=round(best[2], 2))


# ---------------------------------------------------------------- composite
def base_timeline():
    for f in ("timeline_text.mov", "timeline_prores.mov"):
        p = os.path.join(ROOT, "work", f)
        if os.path.exists(p):
            return p
    return None


def cmd_composite():
    plan = json.load(open(os.path.join(ROOT, arg("--plan", "assets/motion_plan.json")), encoding="utf-8"))
    base = arg("--base") or base_timeline() or sys.exit("no work/timeline_text.mov or timeline_prores.mov")
    base = base if os.path.isabs(base) else os.path.join(ROOT, base)
    out = arg("--out", os.path.join(ROOT, "work", "timeline_motion.mov"))
    bdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", base],
                                capture_output=True, text=True).stdout)
    ins, fg, last = ["-i", base], ["[0:v]format=yuv444p10le[b0]"], "b0"
    for k, item in enumerate(sorted(plan, key=lambda p: p["start"]), 1):
        mov = os.path.join(WORK, item["id"] + ".mov")
        if not os.path.exists(mov):
            sys.exit(f"missing {mov}: render it first")
        rj = os.path.join(WORK, item["id"] + ".json")
        if os.path.exists(rj) and not json.load(open(rj))["safe_zone_ok"] and not item.get("allow_outside"):
            sys.exit(f"{item['id']} failed the safe-zone check: fix and re-render, or set allow_outside in the plan")
        odur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mov],
                                    capture_output=True, text=True).stdout)
        if item["start"] + odur > bdur + 0.02:
            print(f"warning: {item['id']} runs past the end of the timeline ({item['start'] + odur:.2f} s > {bdur:.2f} s)")
        ins += ["-i", mov]
        # HyperFrames ProRes is BT.601 limited and untagged: convert to the timeline's BT.709 before blending
        fg.append(f"[{k}:v]scale=in_color_matrix=bt601:in_range=tv:out_color_matrix=bt709:out_range=tv,"
                  f"format=yuva444p10le,setpts=PTS-STARTPTS+{item['start']:.3f}/TB[o{k}]")
        fg.append(f"[{last}][o{k}]overlay=eof_action=pass:format=yuv444p10:alpha=straight[b{k}]")
        last = f"b{k}"
    fg.append(f"[{last}]format=yuv422p10le[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fg), "-map", "[v]",
                    "-r", str(FPS), *ENC, out], check=True)
    n_in = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                               "stream=nb_read_frames", "-of", "csv=p=0", base], capture_output=True, text=True).stdout)
    n_out = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                "stream=nb_read_frames", "-of", "csv=p=0", out], capture_output=True, text=True).stdout)
    print(f"{out}: {n_out} frames (base {n_in})" + ("" if n_in == n_out else "  FRAME COUNT MISMATCH"))
    if arg("--preview"):                                                     # same encode as 60/93 previews
        pv = os.path.join(ROOT, "previews", f"rough_cut_v{arg('--preview')}.mp4")
        os.makedirs(os.path.dirname(pv), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", out, "-vf",
                        "scale=in_range=tv:out_range=tv,format=yuv420p,limiter=min=16:max=235:planes=1",
                        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", "30",
                        "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-an", "-map_metadata", "-1", "-movflags", "+faststart", pv], check=True)
        print(pv)
    sys.exit(0 if n_in == n_out else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"list": cmd_list, "map": cmd_map, "render": cmd_render, "composite": cmd_composite}.get(
        cmd, lambda: sys.exit(__doc__))()
