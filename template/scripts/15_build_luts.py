"""Phase 4.2: build per-camera BASE match LUTs and 3 creative LOOK LUTs (33^3 .cube).
Pipeline order for every shot:  input transform (Phase 2) -> shot repairs (Phase 3)
                                 -> base_<camera>.cube -> look_<n>.cube
Base-match parameters are derived from assets/camera_match_stats.json (measured), and the
script re-measures matched regions after the base LUT to verify convergence.
Output: assets/looks/*.cube, assets/looks/base_match_report.json"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_color import (rgb_to_oklab, oklab_to_rgb, lch, from_lch, hue_weight, smoothstep, soft_shoulder,
                       s_curve, chroma_compress, to_lin, to_disp, write_cube, gamut_map, tone_L)

OUT = os.path.join(ROOT, "assets", "looks"); os.makedirs(OUT, exist_ok=True)
S = json.load(open(os.path.join(ROOT, "assets", "camera_match_stats.json")))

# ---------------- measured targets ----------------
ins_all, sam_all = S["insta_all"], S["samsung_all"]
# WB: NO correction. Phase 4 check of large sunlit neutrals in Insta360 views (asphalt
# a*=0.5 b*=+3.2; courtyard paving a*=0.5 b*=+2.3; bridge concrete a*=-1.2 b*=-1.4) shows
# neutral-to-sunlit-warm rendering. Earlier cyan readings on clouds/granite were sky-light and
# surface colour; a gain derived from them turned asphalt pink (seen in grid v1). Rejected.
wb_gain = np.array([1.0, 1.0, 1.0])
target_sky_C = (ins_all["clear_sky"]["C"] + sam_all["clear_sky"]["C"] * 1.3) / 2
target_green_C = (ins_all["green"]["C"] + sam_all["green"]["C"] * 1.3) / 2
ins_sat = target_green_C / ins_all["green"]["C"]                   # global chroma factor
ins_sky_extra = (target_sky_C / ins_all["clear_sky"]["C"]) / ins_sat
sam_sat = 1.30
PARAMS = dict(insta_wb_gain=wb_gain.round(4).tolist(), insta_sat=round(ins_sat, 3),
              insta_sky_extra=round(ins_sky_extra, 3), samsung_sat=sam_sat,
              target_sky_C_cielab=round(target_sky_C, 1), target_green_C_cielab=round(target_green_C, 1))
print("base params:", PARAMS)

SKY_HUE, SKY_W = 255.0, 45.0      # OKLab hue of blue sky (deg) and half-width
GREEN_HUE, GREEN_W = 135.0, 40.0  # OKLab hue of foliage greens


def base_insta(rgb):
    # chroma only: global + extra on sky hues (no WB, no tone change)
    L, C, h = lch(rgb_to_oklab(rgb))
    k = ins_sat * (1 + (ins_sky_extra - 1) * hue_weight(h, SKY_HUE, SKY_W))
    C = C * k
    return np.clip(oklab_to_rgb(from_lch(L, gamut_map(L, C, h), h)), 0, 1)


def base_samsung(rgb):
    # tone on OKLab L (hue-preserving): gentle normalisation of the flat phone rendering
    L, C, h = lch(rgb_to_oklab(rgb))
    L2 = tone_L(L, contrast=0.08, knee=0.88, white=1.0, gain=1.04)
    # chroma +30% with soft compression so saturated temple paint doesn't blow out
    C2 = chroma_compress(C * sam_sat, 0.16, 0.26)
    return np.clip(oklab_to_rgb(from_lch(L2, gamut_map(L2, C2, h), h)), 0, 1)


def look(rgb, *, contrast, shoulder_knee, black_lift, warm_hi, warm_mid, cool_shadow,
         green_C, green_L, sky_C, sky_L, sat, sat_limit):
    """Shared look builder. Units: OKLab (L 0..1, a/b ~ +-0.3)."""
    # tone on OKLab L only (hue-preserving): S-curve, highlight roll-off, black lift (fade)
    lab = rgb_to_oklab(np.clip(rgb, 0, 1))
    L, C, h = lch(lab)
    L = tone_L(L, contrast=contrast, knee=shoulder_knee, white=0.985, lift=black_lift)
    lab = from_lch(L, C, h)
    # warmth: split by luminance (warm sun in highlights/mids, optional mild cool shadows)
    hi = smoothstep(0.55, 0.9, L); sh = 1 - smoothstep(0.15, 0.45, L); mid = 1 - hi - sh
    a = lab[:, 1] + 0.002 * (warm_hi * hi + warm_mid * mid) - 0.0006 * cool_shadow * sh
    b = lab[:, 2] + 0.006 * (warm_hi * hi + warm_mid * mid) - 0.004 * cool_shadow * sh
    L, C, h = lch(np.stack([L, a, b], -1))
    # secondaries (broad, C-weighted, small): richer greens, deeper skies
    cw = smoothstep(0.02, 0.06, C)                       # only already-coloured pixels
    gw = hue_weight(h, GREEN_HUE, GREEN_W) * cw
    sw = hue_weight(h, SKY_HUE, SKY_W) * cw
    C = C * (1 + green_C * gw) * (1 + sky_C * sw) * sat
    L = L - green_L * gw * 0.01 - sky_L * sw * 0.01
    C = chroma_compress(C, sat_limit * 0.75, sat_limit)
    return np.clip(oklab_to_rgb(from_lch(L, gamut_map(L, C, h), h)), 0, 1)


LOOKS = {
    "look1_natural":  dict(contrast=0.10, shoulder_knee=0.82, black_lift=0.000, warm_hi=1.0, warm_mid=0.5, cool_shadow=0.0,
                           green_C=0.06, green_L=1.5, sky_C=0.04, sky_L=1.5, sat=1.00, sat_limit=0.26),
    "look2_warm_cinematic": dict(contrast=0.18, shoulder_knee=0.78, black_lift=0.012, warm_hi=2.2, warm_mid=1.0, cool_shadow=0.3,
                           green_C=0.12, green_L=3.0, sky_C=0.08, sky_L=3.0, sat=1.03, sat_limit=0.25),
    "look3_filmic":   dict(contrast=0.28, shoulder_knee=0.72, black_lift=0.025, warm_hi=3.0, warm_mid=1.2, cool_shadow=0.8,
                           green_C=0.10, green_L=5.0, sky_C=0.06, sky_L=4.0, sat=0.97, sat_limit=0.22),
}

write_cube(os.path.join(OUT, "base_insta360.cube"), base_insta, title="base match Insta360")
write_cube(os.path.join(OUT, "base_samsung.cube"), base_samsung, title="base match Samsung S24U")
for name, p in LOOKS.items():
    write_cube(os.path.join(OUT, f"{name}.cube"), lambda x, p=p: look(x, **p), title=name)
json.dump(dict(params=PARAMS, looks=LOOKS), open(os.path.join(OUT, "lut_params.json"), "w"), indent=1)
print("wrote", sorted(os.listdir(OUT)))
