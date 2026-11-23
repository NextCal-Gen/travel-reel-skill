"""Phase 3b: turn measurements (assets/diagnostics.csv) into repair decisions (assets/repairs.csv).
Calibrated rules (reasons logged in each row):
  - clipped highlights: views facing the sun clip 20-32% (unrecoverable sky/sun). Logged as
    'avoid view' when > 15% (selection guidance), 'roll-off' when 2-15%.
  - WB cast: a camera WB error is clip-wide, so the rule uses the median a*/b* over ALL views
    of a clip; per-view differences are scene colour, not cast.
  - banding risk: every 8-bit outdoor view has large smooth sky -> one global action.
  - haze: dark-channel + low band contrast, then confirmed or rejected visually
    (VISUAL_REVIEW below records what was seen).
  - motion (ND/shake), underexposure, noise: per view, thresholds from 11_diagnostics.TH."""
import csv, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

TH = dict(clip_rolloff=2.0, clip_avoid=15.0, under_mean_Y=0.22, haze_dc=0.28, haze_contrast=0.55,
          wb_a=3.0, wb_b=5.0, noise=3.0, jitter=1.2, nd_flow=4.0, nd_lap=55.0)

# Visual confirmations of measured triggers (frames viewed in assets/diag_views/)
VISUAL_REVIEW = {
    ("20261002_103422.mp4", "full 9:16", "haze"): ("confirmed", "distant hills washed out, low contrast, grey-blue veil"),
    ("VID_20261002_110214_00_015_003301.mp4", "yaw+0", "haze"): ("rejected", "false positive: bright grey asphalt raises dark channel; distance is clear"),
    ("VID_20261002_100654_00_010_002731.mp4", "*", "wb_cast"): ("rejected as per-clip cast",
        "teal-painted pond structure + water dominate the neutral mask (pedestal a*=-23.7); statue a*=-7.3 "
        "and clouds a*~-5 are sky-light/surface colour. Phase 4 check of large sunlit neutrals (asphalt "
        "a*=0.5 b*=+3.2, paving a*=0.5 b*=+2.3, concrete a*=-1.2 b*=-1.4): no camera-wide cast either"),
}

d = list(csv.DictReader(open(os.path.join(ROOT, "assets", "diagnostics.csv"))))
f = lambda r, k: float(r[k])
out = []
def add(r, diag, val, thr, action, why, status="candidate"):
    out.append(dict(clip=r["clip"] if r else "ALL", view=r["view"] if r else "all", diagnostic=diag,
                    value=round(val, 3) if val is not None else "", threshold=thr, status=status,
                    action_if_selected=action, why=why))

clips = sorted({r["clip"] for r in d})
for clip in clips:
    rows = [r for r in d if r["clip"] == clip]
    # clip-wide WB
    a = np.nanmedian([f(r, "wb_a") for r in rows]); b = np.nanmedian([f(r, "wb_b") for r in rows])
    if abs(a) > TH["wb_a"] or abs(b) > TH["wb_b"]:
        st, note = VISUAL_REVIEW.get((clip, "*", "wb_cast"), ("needs visual check", ""))
        add({"clip": clip, "view": "all views"}, "wb_cast", max(abs(a), abs(b)),
            f"clip-median |a*|>{TH['wb_a']} or |b*|>{TH['wb_b']}",
            "none" if st.startswith("rejected") else "WB correction",
            f"clip-median a*={a:.1f} b*={b:.1f}; visual: {note}", status=st)
    for r in rows:
        c = f(r, "clipped_pct")
        if c > TH["clip_avoid"]:
            add(r, "clipped_highlights", c, f">{TH['clip_avoid']}%", "AVOID this direction (sun/sky clipped, unrecoverable)",
                "sun-facing view", status="selection-guidance")
        elif c > TH["clip_rolloff"]:
            add(r, "clipped_highlights", c, f">{TH['clip_rolloff']}%", "highlight roll-off; clipped data not recoverable",
                "median % pixels with a channel at max")
        if f(r, "mean_Y") < TH["under_mean_Y"]:
            add(r, "underexposure", f(r, "mean_Y"), f"<{TH['under_mean_Y']}", "exposure lift before grade; re-check noise after lift",
                f"noise sigma before lift = {f(r, 'noise_sigma'):.2f}")
        if f(r, "haze_dark_channel") > TH["haze_dc"] and f(r, "band_contrast") < TH["haze_contrast"]:
            st, note = VISUAL_REVIEW.get((clip, r["view"], "haze"), ("needs visual check", ""))
            add(r, "haze", f(r, "haze_dark_channel"), f">{TH['haze_dc']} & contrast<{TH['haze_contrast']}",
                "mild dehaze / local contrast on this shot only" if st != "rejected" else "none",
                f"band_contrast={f(r, 'band_contrast'):.2f}; visual: {note}", status=st)
        if f(r, "noise_sigma") > TH["noise"]:
            add(r, "noise", f(r, "noise_sigma"), f">{TH['noise']}", "temporal denoise before grade", "Immerkaer sigma")
        if f(r, "jitter_px") > TH["jitter"]:
            add(r, "shake", f(r, "jitter_px"), f">{TH['jitter']}px", "vidstab (no gyro data); confirm it is shake, not intended move",
                f"flow={f(r, 'flow_px'):.1f}px")
        if f(r, "flow_px") > TH["nd_flow"] and f(r, "lapvar_motion") > TH["nd_lap"]:
            add(r, "needs_ND", f(r, "flow_px"), f"flow>{TH['nd_flow']}px & lapvar>{TH['nd_lap']}",
                "ND emulation (60p sources: blend frame pairs; 30p sources: RIFE 2x then blend)",
                f"lapvar={f(r, 'lapvar_motion'):.0f}")
add(None, "banding_risk", None, "all sources 8-bit; smooth sky in 50/51 views",
    "GLOBAL: no sky secondaries, fine grain before final 8-bit encode", "smooth_sky_pct median 33%", status="global")
add(None, "lens_distortion", None, "n/a", "none",
    "360 views are rectilinear by construction; Samsung main lens already corrected in-camera; no profile needed", status="not applicable")

with open(os.path.join(ROOT, "assets", "repairs.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
import collections
print(collections.Counter((o["diagnostic"], o["status"]) for o in out))
for o in out:
    if o["diagnostic"] not in ("clipped_highlights",):
        print(o["clip"][:30], o["view"], o["diagnostic"], o["value"], o["status"], "|", o["why"])
