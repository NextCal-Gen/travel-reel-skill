"""Privacy detectors (Phase 5 avoid-zones and Phase 8 per-frame scan).
 - Faces: OpenCV YuNet ($TRAVEL_REEL_MODELS/face_detection_yunet_2023mar.onnx, sha256 verified).
 - Persons: Ultralytics YOLO11n ($TRAVEL_REEL_MODELS/yolo11n.pt), class 0 = person.
Both run on RGB uint8 frames of what the reel actually shows (rectilinear 9:16 views)."""
import os
import cv2, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.environ.get("TRAVEL_REEL_MODELS", os.path.expanduser("~/travel-reel-toolkit/models"))   # shared toolkit
_face, _yolo = {}, None

FACE_SCORE = 0.6      # YuNet default is 0.9; lowered on purpose: a false alarm costs a review, a miss costs privacy


def faces(rgb8, score=FACE_SCORE):
    """Returns list of (x, y, w, h, score). Runs at native size and 2x upscaled (small faces)."""
    out = []
    for scale in (1.0, 2.0):
        img = cv2.resize(rgb8, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1 else rgb8
        h, w = img.shape[:2]
        key = (w, h)
        if key not in _face:
            _face[key] = cv2.FaceDetectorYN.create(os.path.join(MODELS, "face_detection_yunet_2023mar.onnx"),
                                                   "", (w, h), score, 0.3, 5000)
        _, det = _face[key].detect(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        if det is not None:
            for d in det:
                x, y, ww, hh = (d[:4] / scale).tolist()
                out.append((x, y, ww, hh, float(d[14])))
    # merge duplicates from the two scales
    keep = []
    for f in sorted(out, key=lambda f: -f[4]):
        if all(_iou(f, k) < 0.3 for k in keep):
            keep.append(f)
    return keep


def persons(rgb8, conf=0.25):
    """Returns list of (x, y, w, h, conf) for class 'person'."""
    global _yolo
    if _yolo is None:
        from ultralytics import YOLO
        _yolo = YOLO(os.path.join(MODELS, "yolo11n.pt"))
    r = _yolo.predict(rgb8[..., ::-1], conf=conf, classes=[0], verbose=False, imgsz=960)[0]
    return [(float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1]), float(c))
            for b, c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy())]


def _iou(a, b):
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0, min(ax2, bx2) - max(a[0], b[0])); ih = max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)
