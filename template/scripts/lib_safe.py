"""Instagram Reels safe zone for a 1080x1920 frame: one definition for captions (lib_text), the route
map (91) and motion graphics (70 + template/motion/assets/common.js, which repeats these numbers).

  top 220 / bottom 1470: the account row, caption text and audio line cover the bottom,
                         the Reels header the top.
  left/right 70:         design margin (Instagram's own minimum is 35).
  x 980 from y 1155 down: the like / comment / share / remix button column."""
import numpy as np

W, H = 1080, 1920
SAFE = dict(top=220, bottom=1470, left=70, right=W - 70, btn_top=1155, btn_right=980, ig_min_side=35)


def fit_box(x0, y0, x1, y1):
    """Shift a box (keeping its size) so it sits inside the safe zone, including the button column."""
    w, h = x1 - x0, y1 - y0
    y0 = min(max(y0, SAFE["top"]), SAFE["bottom"] - h)
    right = SAFE["btn_right"] if y0 + h > SAFE["btn_top"] else SAFE["right"]
    x0 = min(max(x0, SAFE["left"]), right - w)
    x0 = max(x0, SAFE["left"])
    return x0, y0, x0 + w, y0 + h


def box_ok(x0, y0, x1, y1):
    if y0 < SAFE["top"] or y1 > SAFE["bottom"] or x0 < SAFE["left"] or x1 > SAFE["right"]:
        return False
    return not (y1 > SAFE["btn_top"] and x1 > SAFE["btn_right"])


def violations(alpha, thr=64):
    """Opaque-ish pixels (alpha > thr of 255) outside the zone, for a rendered overlay's alpha plane.
    Soft shadows and glows below the threshold are ignored; side check uses Instagram's 35 px minimum."""
    m = alpha > thr
    if not m.any():
        return None
    ys, xs = np.nonzero(m)
    out = {}
    if ys.min() < SAFE["top"]:
        out["above_top"] = int(SAFE["top"] - ys.min())
    if ys.max() > SAFE["bottom"]:
        out["below_bottom"] = int(ys.max() - SAFE["bottom"])
    if xs.min() < SAFE["ig_min_side"] or xs.max() > W - SAFE["ig_min_side"]:
        out["sides"] = [int(xs.min()), int(xs.max())]
    low = m[SAFE["btn_top"]:, SAFE["btn_right"]:]
    if low.any():
        out["button_column_px"] = int(low.sum())
    return out or None
