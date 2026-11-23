"""Colour math for camera matching and looks.
Working space in/out: display-referred Rec.709 / BT.1886 RGB in [0,1].
Operations happen in OKLab (perceptual, hue-linear) after decoding gamma 2.4.
Every transform is baked into a .cube 3D LUT so ffmpeg lut3d applies exactly the same math."""
import numpy as np

GAMMA = 2.4


def to_lin(v):  return np.power(np.clip(v, 0, None), GAMMA)
def to_disp(v): return np.power(np.clip(v, 0, None), 1 / GAMMA)

# Rec.709 linear RGB -> OKLab (Rec.709 primaries == sRGB primaries)
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M1i, _M2i = np.linalg.inv(_M1), np.linalg.inv(_M2)


def rgb_to_oklab(rgb_disp):
    lms = to_lin(rgb_disp) @ _M1.T
    return np.cbrt(lms) @ _M2.T


def oklab_to_rgb(lab):
    lms = (lab @ _M2i.T) ** 3
    return to_disp(np.clip(lms @ _M1i.T, 0, None))


def lch(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    return L, np.hypot(a, b), np.arctan2(b, a)


def from_lch(L, C, h):
    return np.stack([L, C * np.cos(h), C * np.sin(h)], -1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def hue_weight(h, center_deg, width_deg):
    """Smooth raised-cosine weight around a hue (OKLab hue angle, degrees)."""
    d = np.degrees(np.angle(np.exp(1j * (h - np.radians(center_deg)))))
    return np.where(np.abs(d) < width_deg, 0.5 * (1 + np.cos(np.pi * d / width_deg)), 0.0)


def soft_shoulder(y, knee=0.8, white=1.0):
    """Highlight roll-off on display values: identity below knee, smooth compression above
    so the old range [knee, 1+] approaches `white` asymptotically (never hard clips)."""
    over = np.clip(y - knee, 0, None)
    span = white - knee
    return np.where(y > knee, knee + span * (1 - np.exp(-over / span)), y)


def s_curve(y, amount):
    """Symmetric S-curve on [0,1]: fixes 0, 0.5, 1; slope 1+amount at mid, 1-amount at ends.
    Monotonic for |amount| < 1."""
    return y - amount * np.sin(2 * np.pi * y) / (2 * np.pi)


def chroma_compress(C, thresh, limit):
    """Soft-limit chroma above thresh toward limit (prevents oversaturation)."""
    over = np.clip(C - thresh, 0, None)
    span = limit - thresh
    return np.where(C > thresh, thresh + span * (1 - np.exp(-over / span)), C)


def gamut_map(L, C, h, iters=14):
    """Hue- and lightness-preserving gamut mapping: for colours that fall outside [0,1] RGB,
    bisect chroma down until they fit (no per-channel clipping -> no hue shifts)."""
    def inside(Cx):
        rgb = oklab_to_rgb(from_lch(L, Cx, h))
        lin = (from_lch(L, Cx, h) @ _M2i.T) ** 3 @ _M1i.T
        return np.all((lin >= -1e-4) & (lin <= 1 + 1e-4), axis=-1)
    ok = inside(C)
    lo, hi = np.zeros_like(C), C.copy()
    for _ in range(iters):
        mid = (lo + hi) / 2
        good = inside(mid)
        lo = np.where(good, mid, lo); hi = np.where(good, hi, mid)
    return np.where(ok, C, lo)


def tone_L(L, contrast=0.0, knee=None, white=0.985, lift=0.0, gain=1.0):
    """Tone curve applied to OKLab L only (hue-preserving). L ~ perceptual lightness 0..1."""
    y = np.clip(L * gain, 0, None)
    if contrast:
        y = s_curve(np.clip(y, 0, 1), contrast)
    if knee is not None:
        y = soft_shoulder(y, knee=knee, white=white)
    return lift + (1 - lift) * y


# ---------- LUT IO ----------
def lut_grid(n=33):
    r = np.linspace(0, 1, n)
    b, g, rr = np.meshgrid(r, r, r, indexing="ij")   # .cube order: R fastest
    return np.stack([rr, g, b], -1).reshape(-1, 3)


def write_cube(path, fn, n=33, title="look"):
    grid = lut_grid(n)
    out = np.clip(fn(grid), 0, 1)
    with open(path, "w") as fh:
        fh.write(f'TITLE "{title}"\nLUT_3D_SIZE {n}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        for v in out:
            fh.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")


def read_cube(path):
    rows, n = [], None
    for line in open(path):
        s = line.strip()
        if s.startswith("LUT_3D_SIZE"): n = int(s.split()[1])
        elif s and (s[0].isdigit() or s[0] == "-" or s[0] == "."): rows.append([float(x) for x in s.split()])
    return np.array(rows, np.float32).reshape(n, n, n, 3), n   # [b][g][r]


def apply_cube(img, lut_n):
    """Trilinear LUT application (matches ffmpeg lut3d interp=trilinear)."""
    lut, n = lut_n
    x = np.clip(img, 0, 1) * (n - 1)
    i0 = np.floor(x).astype(int); i0 = np.clip(i0, 0, n - 2); f = x - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    def L(bb, gg, rr): return lut[bb, gg, rr]
    c000 = L(b0, g0, r0); c100 = L(b0, g0, r0 + 1); c010 = L(b0, g0 + 1, r0); c110 = L(b0, g0 + 1, r0 + 1)
    c001 = L(b0 + 1, g0, r0); c101 = L(b0 + 1, g0, r0 + 1); c011 = L(b0 + 1, g0 + 1, r0); c111 = L(b0 + 1, g0 + 1, r0 + 1)
    c00 = c000 * (1 - fr) + c100 * fr; c10 = c010 * (1 - fr) + c110 * fr
    c01 = c001 * (1 - fr) + c101 * fr; c11 = c011 * (1 - fr) + c111 * fr
    c0 = c00 * (1 - fg) + c10 * fg; c1 = c01 * (1 - fg) + c11 * fg
    return c0 * (1 - fb) + c1 * fb
