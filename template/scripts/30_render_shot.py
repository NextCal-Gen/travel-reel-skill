"""Phase 6: render EDL shots from ORIGINALS to 10-bit ProRes 422 HQ, 1080x1920, 30 fps.
Chain (per shot):
  decode -> input transform (range fix / relabel) -> working RGB 16-bit (zscale, explicit)
  -> geometry  : 360 = v360 eased keyframes via sendcmd | flat = crop keyframes via sendcmd + scale
  -> motion    : none = fps 30 (60p: every other frame) | blend2 = tmix 2 @60p then fps 30
                 rife_blend = (30p source) RIFE x2 to 60p, tmix 2, fps 30
  -> repair LUT (only if triggered) -> base_<camera>.cube -> look2_warm_cinematic.cube
  -> yuv422p10le limited BT.709 tagged -> ProRes 422 HQ    (no grain here; grain at final export)
Usage: 30_render_shot.py [S01 S02 ...]   (default: all)   Output: work/shots/<id>.mov"""
import os, shutil, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT, inventory, input_transform, range_of, to_working_rgb
from lib_edl import load_edl, interp, vfov, flat_crop, OUT_W, OUT_H

LK = os.path.join(ROOT, "assets", "looks")
OUT = os.path.join(ROOT, "work", "shots"); os.makedirs(OUT, exist_ok=True)
RIFE = os.environ.get("RIFE_BIN", os.path.expanduser("~/travel-reel-toolkit/rife/rife-ncnn-vulkan"))   # shared toolkit
RIFE_MODEL_DIR = os.environ.get("RIFE_MODEL_DIR", os.path.dirname(RIFE))
REPAIR_LUT = {"S02": "repair_S02_dehaze.cube", "S06": "repair_S06_exposure.cube"}
FINISH_LUT = {"S02": "finish_S02_sand.cube"}   # Phase 10 trims, applied after the look (71_finishing_trims.py)
LOOK = "look2_warm_cinematic.cube"
inv = inventory()
FPS = 30


SHUTTER = 1 / 60          # 180-degree shutter at 30 fps
ROT_PAD = 160             # wrap padding (px) so the blur is continuous across the equirect seam


def rot_blur_sigma(s, t, eq_w):
    """Motion blur for a VIRTUAL yaw rotation: a yaw turn is a pure horizontal shift of the
    equirect, so the exposure smear is a horizontal box of length |dyaw/dt| * shutter * px_per_deg.
    Gaussian with equal variance: sigma = L / sqrt(12)."""
    h = 1e-3
    w = abs(interp(s["kf"], t + h)[0] - interp(s["kf"], max(0.0, t - h))[0]) / (2 * h if t >= h else h)
    L = w * SHUTTER * eq_w / 360.0
    return L / np.sqrt(12) if L >= 1.0 else 0.0


def cmd_file(s, src_fps, kind, src_w=None, src_h=None):
    """sendcmd script: one command block per source frame time (relative to shot start)."""
    lines = []
    n = int(np.ceil(s["dur"] * src_fps)) + 2
    for i in range(n):
        t = i / src_fps
        if kind == "360":
            yaw, pitch, hf = interp(s["kf"], t)
            yaw = (yaw + 180.0) % 360.0 - 180.0      # v360 accepts -180..180; keyframes may be unwrapped (spins)
            cmd = f"{t:.4f} v360 yaw {yaw:.3f}, v360 pitch {pitch:.3f}, v360 h_fov {hf:.3f}, v360 v_fov {vfov(hf):.3f}"
            if s["nd"] == "rot_blur":
                cmd += f", gblur sigma {rot_blur_sigma(s, t, src_w):.3f}"
            lines.append(cmd + ";")
        else:
            z, cx, cy = interp(s["kf"], t)
            x, y, w, h = flat_crop(src_w, src_h, z, cx, cy)
            lines.append(f"{t:.4f} crop w {w}, crop h {h}, crop x {x}, crop y {y};")
    p = os.path.join(OUT, f"{s['id']}_cmd.txt")
    open(p, "w").write("\n".join(lines) + "\n")
    return p


def grade_chain(s, row):
    base = "base_insta360.cube" if s["kind"] == "360" else "base_samsung.cube"
    luts = (([REPAIR_LUT[s["id"]]] if s["id"] in REPAIR_LUT else []) + [base, LOOK]
            + ([FINISH_LUT[s["id"]]] if s["id"] in FINISH_LUT else []))
    return ",".join(f"lut3d=file={LK}/{l}:interp=tetrahedral" for l in luts)


ENC = ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le",
       "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-an"]
# LUT output carries no colour tags -> state them explicitly (full-range RGB, BT.709) or zscale
# has "no path between colorspaces".
TO_YUV = ("setparams=range=pc:color_primaries=bt709:color_trc=bt709:colorspace=gbr,"
          "zscale=range=limited:matrix=709:primaries=709:transfer=709,format=yuv422p10le")


def render(s):
    row = inv[s["clip"]]
    src_fps = float(row["fps"])
    out = os.path.join(OUT, f"{s['id']}.mov")
    pre = input_transform(row) + "," + to_working_rgb(range_of(row))
    if s["kind"] == "360":
        hf0 = s["kf"][0][3]
        eq_w = int(row["resolution"].split("x")[0])
        blur = ""
        if s["nd"] == "rot_blur":
            # wrap-pad -> horizontal-only gaussian (sigmaV=0, keyframed via sendcmd) -> unpad
            blur = (f"split=3[rb_a][rb_b][rb_c];[rb_a]crop={ROT_PAD}:ih:iw-{ROT_PAD}:0[rb_l];[rb_c]crop={ROT_PAD}:ih:0:0[rb_r];"
                    f"[rb_l][rb_b][rb_r]hstack=3,gblur=sigma=0:sigmaV=0:steps=3,crop=iw-{2 * ROT_PAD}:ih:{ROT_PAD}:0,")
        geo = (f"sendcmd=f={cmd_file(s, src_fps, '360', eq_w)},{blur}"
               f"v360=input=e:output=flat:yaw={s['kf'][0][1]}:pitch={s['kf'][0][2]}:h_fov={hf0}:v_fov={vfov(hf0):.3f}"
               f":w={OUT_W}:h={OUT_H}:interp=lanczos:reset_rot=1")
        # reset_rot=1 is REQUIRED: without it v360 composes each yaw/pitch command onto the
        # current orientation (measured: 60/255 error after 12 frames; camera spun to sky/ground).
    else:
        sw, sh = 2160, 3840   # all flat sources are 4K portrait after autorotate
        x, y, w, h = flat_crop(sw, sh, *s["kf"][0][1:])
        geo = (f"sendcmd=f={cmd_file(s, src_fps, 'flat', sw, sh)},crop=w={w}:h={h}:x={x}:y={y}:exact=1,"
               f"scale={OUT_W}:{OUT_H}:flags=lanczos")
    grade = grade_chain(s, row)
    seek = ["-ss", f"{s['tin']:.3f}", "-t", f"{s['dur'] + 0.1:.3f}", "-i", os.path.join(ROOT, "raw", s["clip"])]
    if s["nd"] == "rife_blend":
        # 1) geometry at native 30p -> 8-bit PNG frames (RIFE is 8-bit only: documented precision cost)
        fdir = os.path.join(OUT, f"{s['id']}_frames"); idir = fdir + "_x2"
        for d in (fdir, idir): shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        subprocess.run(["ffmpeg", "-v", "error", "-y", *seek, "-vf", f"{pre},{geo},format=rgb24",
                        os.path.join(fdir, "%05d.png")], check=True)
        nin = len(os.listdir(fdir))
        subprocess.run([RIFE, "-i", fdir, "-o", idir, "-m", os.path.join(RIFE_MODEL_DIR, "rife-v4.6"),
                        "-n", str(nin * 2), "-f", "%05d.png"], check=True, capture_output=True)
        # 2) blend pairs at 60p -> 30p, then grade (frames are already working-space RGB)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(src_fps * 2), "-i", os.path.join(idir, "%05d.png"),
                        "-vf", f"format=gbrp16le,tmix=frames=2:weights=1 1,fps={FPS},{grade},{TO_YUV}",
                        "-t", f"{s['dur']:.3f}", *ENC, out], check=True)
        shutil.rmtree(fdir); shutil.rmtree(idir)
    else:
        if s["nd"] == "blend2":
            motion = f"tmix=frames=2:weights=1 1,fps={FPS}"
            vf = f"{pre},{geo},{motion},{grade},{TO_YUV}"
        else:
            vf = f"fps={FPS},{pre},{geo},{grade},{TO_YUV}"   # decimate first (cheaper), then geometry
        subprocess.run(["ffmpeg", "-v", "error", "-y", *seek, "-vf", vf, "-t", f"{s['dur']:.3f}", *ENC, out], check=True)
    os.remove(os.path.join(OUT, f"{s['id']}_cmd.txt")) if os.path.exists(os.path.join(OUT, f"{s['id']}_cmd.txt")) else None
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                         "stream=width,height,r_frame_rate,nb_read_frames,pix_fmt", "-of", "csv=p=0", out],
                        capture_output=True, text=True).stdout.strip()
    print(f"{s['id']} {s['nd']:10s} -> {pr}  (expected frames {round(s['dur'] * FPS)})")


want = sys.argv[1:]
for s in load_edl():
    if s["kind"] == "graphic":
        continue          # rendered by its own script (e.g. 91_route_map.py)
    if not want or s["id"] in want:
        render(s)
