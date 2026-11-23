"""Shared helpers for the travel-reel pipeline.
Single source of truth for per-clip input transforms (Phase 2), loaded from
assets/source_inventory.csv so every later script decodes clips identically."""
import csv, json, os, subprocess
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")


def inventory():
    with open(os.path.join(ROOT, "assets", "source_inventory.csv")) as fh:
        return {r["filename"]: r for r in csv.DictReader(fh)}


def is360(row):
    return row["type"].startswith("A")


def input_transform(row):
    """ffmpeg filter prefix that puts a clip into the working space:
    SDR Rec.709 / BT.1886 (gamma 2.4) with the *correct* range interpretation.
    No colour transform is needed for any clip in this set (all SDR, no Log)."""
    rng = "pc" if row["range"].startswith("full") else "tv"
    # 1) explicit value-preserving relabel to yuv420p. Without it, a yuvj420p source (clip 003)
    #    gets an auto-inserted full->limited squeeze before zscale, which then squeezes again
    #    (measured: Y10 146/763 instead of 95/820). in_range == out_range -> code values untouched.
    # 2) setparams overrides wrong container tags before any conversion happens.
    return (f"scale=in_range={rng}:out_range={rng}:flags=neighbor,format=yuv420p,"
            f"setparams=range={rng}:color_primaries=bt709:color_trc=bt709:colorspace=bt709")


def range_of(row):
    return "full" if row["range"].startswith("full") else "limited"


def to_working_rgb(rng):
    """THE ONLY YUV->RGB conversion used anywhere in the pipeline (previews, analysis, renders).
    Explicit range/matrix: FFmpeg's auto-inserted converter was measured to IGNORE the
    setparams range override (6.2/255 error vs a manual BT.709 full-range decode), while
    this zscale path matches it to 0.27/255. rng: 'full' | 'limited'."""
    return (f"zscale=rangein={rng}:matrixin=709:primariesin=709:transferin=709:"
            f"range=full:matrix=709:primaries=709:transfer=709,format=gbrp16le")


def to_rgb(width, height, rng, pix="rgb48le", flags="lanczos"):
    """Working-space RGB (16-bit) then geometry in RGB (no further range handling)."""
    return to_working_rgb(rng) + f",scale={width}:{height}:flags={flags},format={pix}"


def to_rgb48(width, height, rng):
    return to_rgb(width, height, rng)


def v360_view(yaw=0, pitch=0, roll=0, h_fov=70, w=1080, h=1920):
    """Rectilinear 9:16 view out of an equirect frame. v_fov derived from aspect."""
    v_fov = float(np.degrees(2 * np.arctan(np.tan(np.radians(h_fov / 2)) * h / w)))
    return (f"v360=input=e:output=flat:yaw={yaw}:pitch={pitch}:roll={roll}:"
            f"h_fov={h_fov}:v_fov={v_fov:.3f}:w={w}:h={h}:interp=lanczos")


def grab_rgb(clip, t, vf_after="", width=1080, height=-2, row=None):
    """Decode one frame at time t as float32 RGB [0,1] in the working space.
    Output width is always `width`; height follows (-2 = keep aspect) and is derived
    from the returned byte count."""
    row = row or inventory()[clip]
    chain = input_transform(row)
    if vf_after:
        chain += "," + vf_after
    chain += "," + to_rgb48(width, height, range_of(row))
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", os.path.join(RAW, clip),
         "-frames:v", "1", "-vf", chain, "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
        capture_output=True, check=True).stdout
    h = len(out) // (width * 3 * 2)
    return np.frombuffer(out, dtype="<u2").reshape(h, width, 3).astype(np.float32) / 65535.0


PROXY_DIR = os.path.join(ROOT, "work", "proxies")


def proxy_path(clip):
    return os.path.join(PROXY_DIR, os.path.splitext(clip)[0] + ".mov")


def grab_proxy_rgb(clip, t, vf_after="", width=540, height=-2):
    """Analysis-only decode from the 10-bit proxy (standard limited-range BT.709, rotation baked)."""
    chain = (vf_after + "," if vf_after else "") + to_rgb(width, height, "limited")
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", proxy_path(clip), "-frames:v", "1",
                          "-vf", chain, "-f", "rawvideo", "-pix_fmt", "rgb48le", "-"],
                         capture_output=True, check=True).stdout
    h = len(out) // (width * 3 * 2)
    return np.frombuffer(out, dtype="<u2").reshape(h, width, 3).astype(np.float32) / 65535.0


_VIEW_MAPS = {}


def equirect_view(eq, yaw, pitch=0.0, h_fov=70.0, w=540, h=960):
    """Analysis-only equirect -> rectilinear remap (final renders use ffmpeg v360).
    Convention verified against ffmpeg v360 (mean |diff| < 2/255 at yaw +-60, pitch +-20):
    same yaw sign, pitch + = look up. (Before 2026-11-22 23:5x the pitch sign was inverted;
    direction sheets were rendered at labelled pitch -5 = actually 5 deg UP in v360 terms.)"""
    pitch = -pitch
    import cv2
    key = (eq.shape[:2], round(yaw, 3), round(pitch, 3), round(h_fov, 3), w, h)
    if key not in _VIEW_MAPS:
        H, W = eq.shape[:2]
        f = (w / 2) / np.tan(np.radians(h_fov / 2))
        x, y = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
        d = np.stack([x, -y, np.full_like(x, f)], -1)
        d /= np.linalg.norm(d, axis=-1, keepdims=True)
        p, yw = np.radians(pitch), np.radians(yaw)
        Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
        Ry = np.array([[np.cos(yw), 0, np.sin(yw)], [0, 1, 0], [-np.sin(yw), 0, np.cos(yw)]])
        d = d @ (Ry @ Rx).T
        lon = np.arctan2(d[..., 0], d[..., 2]); lat = np.arcsin(np.clip(d[..., 1], -1, 1))
        if len(_VIEW_MAPS) > 64: _VIEW_MAPS.clear()
        _VIEW_MAPS[key] = (((lon / np.pi + 1) / 2 * W - 0.5).astype(np.float32),
                           ((0.5 - lat / np.pi) * H - 0.5).astype(np.float32))
    mx, my = _VIEW_MAPS[key]
    return cv2.remap(eq, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def proxy_frames(clip, t0, dur, fps_out, width, height, pix="rgb24"):
    """Yield (t, frame uint8 RGB) from the proxy at fps_out between t0 and t0+dur."""
    chain = f"fps={fps_out}," + to_rgb(width, height, "limited", pix, "area")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", proxy_path(clip),
                          "-vf", chain, "-f", "rawvideo", "-pix_fmt", pix, "-"], capture_output=True, check=True).stdout
    n = len(raw) // (width * height * 3)
    arr = np.frombuffer(raw, np.uint8).reshape(n, height, width, 3)
    for i in range(n):
        yield t0 + i / fps_out, arr[i]


def save_png16(path, rgb):
    import cv2
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, (np.clip(rgb, 0, 1) * 65535 + 0.5).astype(np.uint16)[..., ::-1])


def save_jpg(path, rgb, q=90):
    import cv2
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)[..., ::-1],
                [cv2.IMWRITE_JPEG_QUALITY, q])
