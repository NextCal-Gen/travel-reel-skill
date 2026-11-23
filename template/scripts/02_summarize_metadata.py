"""Phase 1.1b: summarize metadata dumps into assets/metadata_summary.csv (one row per clip).
Pure parsing of assets/metadata/*.json; does not touch raw/."""
import csv, json, glob, os, re
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(ROOT, "assets", "metadata")


def load(p):
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception:
        return None


def exif_find(ex, *keys):
    """Search exiftool -G1 dict for any key whose tag part matches one of keys (case-insensitive)."""
    out = {}
    for k, v in ex.items():
        tag = k.split(":")[-1].lower()
        for want in keys:
            if tag == want.lower():
                out.setdefault(want, v)
    return out


rows = []
for fp in sorted(glob.glob(os.path.join(MD, "*.ffprobe.json"))):
    name = os.path.basename(fp)[: -len(".ffprobe.json")]
    ff = load(fp) or {}
    mi = load(os.path.join(MD, name + ".mediainfo.json")) or {}
    ex = (load(os.path.join(MD, name + ".exiftool.json")) or [{}])[0]

    v = next((s for s in ff.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in ff.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = ff.get("format", {})
    tags = {**fmt.get("tags", {}), **v.get("tags", {})}

    mtracks = mi.get("media", {}).get("track", [])
    mv = next((t for t in mtracks if t.get("@type") == "Video"), {})
    mg = next((t for t in mtracks if t.get("@type") == "General"), {})

    rfr = v.get("r_frame_rate", "0/1")
    afr = v.get("avg_frame_rate", "0/1")
    fr_r = float(Fraction(rfr)) if rfr != "0/0" else 0
    fr_a = float(Fraction(afr)) if afr != "0/0" else 0

    side = v.get("side_data_list", []) or []
    side_types = [s.get("side_data_type", "") for s in side]
    rotation = next((s.get("rotation") for s in side if "rotation" in s), tags.get("rotate", ""))

    e = exif_find(ex, "Make", "Model", "AndroidModel", "AndroidManufacturer", "Software",
                  "ProjectionType", "Spherical", "StitchingSoftware", "GPSCoordinates",
                  "GPSLatitude", "GPSLongitude", "CompressorName", "CameraModelName",
                  "Encoder", "HandlerDescription", "Comment", "Title")
    # Insta360 often writes its model inside an "insta360" atom or Comment
    insta_hint = "; ".join(f"{k}={v}" for k, v in ex.items()
                           if re.search(r"insta|spheric|projection|stitch|gyro|lens", k, re.I))[:300]

    rows.append({
        "file": name,
        "size_MB": round(int(fmt.get("size", 0)) / 1e6, 1),
        "duration_s": round(float(fmt.get("duration", 0)), 2),
        "codec": f'{v.get("codec_name")}/{v.get("profile")}',
        "WxH": f'{v.get("width")}x{v.get("height")}',
        "pix_fmt": v.get("pix_fmt"),
        "bit_depth": mv.get("BitDepth", ""),
        "fps_r": round(fr_r, 3), "fps_avg": round(fr_a, 3),
        "VFR_mi": mv.get("FrameRate_Mode", ""),
        "bitrate_Mbps": round(int(v.get("bit_rate", 0) or 0) / 1e6, 1),
        "range": v.get("color_range", ""),
        "primaries": v.get("color_primaries", ""),
        "transfer": v.get("color_transfer", ""),
        "matrix": v.get("color_space", ""),
        "hdr_mi": mv.get("HDR_Format", "") + (" " + mv.get("HDR_Format_Compatibility", "") if mv.get("HDR_Format_Compatibility") else ""),
        "side_data": "|".join(side_types),
        "rotation": rotation,
        "audio": f'{a.get("codec_name","-")} {a.get("sample_rate","")} {a.get("channels","")}ch' if a else "none",
        "make": e.get("Make") or e.get("AndroidManufacturer", ""),
        "model": e.get("Model") or e.get("AndroidModel") or e.get("CameraModelName", ""),
        "encoder": tags.get("encoder", "") or e.get("Encoder", "") or e.get("CompressorName", ""),
        "software": e.get("Software", ""),
        "gps": e.get("GPSCoordinates", "") or tags.get("location", "") or tags.get("com.apple.quicktime.location.ISO6709", ""),
        "created": tags.get("creation_time", ""),
        "other_tags": "; ".join(f"{k}={v}" for k, v in tags.items()
                                if k not in ("creation_time", "encoder", "handler_name", "vendor_id",
                                             "language", "major_brand", "minor_version",
                                             "compatible_brands"))[:200],
        "insta_hint": insta_hint,
    })

out = os.path.join(ROOT, "assets", "metadata_summary.csv")
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"wrote {out} ({len(rows)} clips)")
