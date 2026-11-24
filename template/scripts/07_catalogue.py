"""Phase P.1: catalogue every clip and group clips into visits (multi-reel planning).
Generic: works for one cafe visit, a ride + stop, a day trip or a multi-day trip.

Reads  assets/metadata/<clip>.exiftool.json   (written by 01_extract_metadata.sh)
       ../visit_types.json or assets/visit_types.json (optional, for OSM -> visit type)
Writes assets/catalogue.csv  one row per clip: time, GPS, movement, visit, day
       assets/visits.csv     one row per visit: kind (stop/transit), time span, centroid, OSM place, suggested type
       assets/scope.json     detected tier + warnings (clock, time zone, missing GPS)

Usage: 07_catalogue.py [--gap-min 20] [--dist-m 300] [--move-kmh 15] [--tz-offset +07:00] [--geocode]
  --geocode   reverse-geocode each visit centroid with OSM Nominatim (sends coordinates to
              nominatim.openstreetmap.org; 1 request/s; cached in assets/geocode_cache.json)
Thresholds are starting values: tune per trip if visits are split or merged wrongly.
kind: transit (GPS shows movement within the clip), stop (GPS, stationary) or unknown (no GPS: Claude
decides from the footage). Claude labels visits visually afterwards (the `type` column); this
script only suggests."""
import csv, glob, json, math, os, re, sys, time, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
ROOT = os.environ.get("PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")


def arg(name, default, cast=str):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


GAP_MIN = arg("--gap-min", 20.0, float)
DIST_M = arg("--dist-m", 300.0, float)
MOVE_KMH = arg("--move-kmh", 15.0, float)
TZ_ARG = arg("--tz-offset", None)
GEOCODE = "--geocode" in sys.argv

# ---------- parsing helpers ----------
DMS = re.compile(r"(\d+(?:\.\d+)?)\s*deg\s*(\d+(?:\.\d+)?)'\s*(\d+(?:\.\d+)?)\"?\s*([NSEW])")
ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")
DATE = re.compile(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def coord(v):
    if isinstance(v, (int, float)):
        return float(v)
    m = DMS.search(str(v))
    if m:
        d = float(m[1]) + float(m[2]) / 60 + float(m[3]) / 3600
        return -d if m[4] in "SW" else d
    try:
        return float(str(v).split()[0])
    except ValueError:
        return None


def pair(v):
    """'lat, lon[, alt]' in DMS or decimal, or ISO 6709 '+12.97+077.59/'."""
    s = str(v)
    d = DMS.findall(s)
    if len(d) >= 2:
        return tuple((-1 if h in "SW" else 1) * (float(a) + float(b) / 60 + float(c) / 3600) for a, b, c, h in d[:2])
    m = ISO6709.match(s.strip())
    if m:
        return float(m[1]), float(m[2])
    parts = [p.strip() for p in s.split(",")]
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    return None


def parse_date(v):
    m = DATE.search(str(v))
    if not m:
        return None, None
    try:                                         # zeroed dates (0000:00:00, e.g. Insta360 app exports) = no date
        dt = datetime(*map(int, m.groups()[:6]))
    except ValueError:
        return None, None
    tz = m[7]
    if tz is None:
        return dt, None
    off = timedelta(0) if tz == "Z" else timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6])) * (1 if tz[0] == "+" else -1)
    return dt, off


def duration_s(v):
    s = str(v).strip()
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    try:
        return float(s.split()[0])
    except ValueError:
        return 0.0


def haversine(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ---------- per-clip extraction ----------
def extract(path):
    d = json.load(open(path))
    d = d[0] if isinstance(d, list) else d
    clip = os.path.basename(path).replace(".exiftool.json", "")
    pts = []
    lat = {k.split(":")[0]: coord(v) for k, v in d.items() if k.endswith("GPSLatitude")}
    lon = {k.split(":")[0]: coord(v) for k, v in d.items() if k.endswith("GPSLongitude")}
    for g in lat:
        if g in lon and lat[g] is not None and lon[g] is not None:
            pts.append((lat[g], lon[g], f"{g}:GPSLatitude"))
    for k, v in d.items():
        if k.endswith(("GPSCoordinates", "GPSPosition", "LocationISO6709", "ISO6709")):
            p = pair(v)
            if p:
                pts.append((p[0], p[1], k))
    pts = [p for p in pts if p[0] is not None and abs(p[0]) <= 90 and abs(p[1]) <= 180 and (p[0], p[1]) != (0.0, 0.0)]

    # timestamp: prefer one with an explicit UTC offset (exact), in tag priority order;
    # else the first offset-less one (QuickTime CreateDate is UTC by spec, but some cameras write local time)
    cands = []
    for prio, suffix in enumerate(("CreationDate", "DateTimeOriginal", "CreateDate", "MediaCreateDate", "TrackCreateDate")):
        for k, v in d.items():
            if k.endswith(suffix) and not k.startswith(("File", "System")):
                dt, o = parse_date(v)
                if dt and dt.year > 1970:
                    cands.append((o is None, prio, dt, o, k))
    t, off, src = None, None, None
    android_tz = None                            # Samsung/Android: UTC dates + the offset in a separate tag (e.g. +0530)
    for k, v in d.items():
        if k.endswith("AndroidTimeZone"):
            m = re.fullmatch(r"\s*([+-])(\d{2}):?(\d{2})\s*", str(v))
            if m: android_tz = timedelta(hours=int(m[2]), minutes=int(m[3])) * (1 if m[1] == "+" else -1)
    if cands:
        no_off, _, dt, o, k = sorted(cands, key=lambda c: (c[0], c[1]))[0]
        if not no_off:
            t, off, src = dt - o, o, k
        elif android_tz is not None:
            t, off, src = dt, android_tz, k + " (UTC) + AndroidTimeZone"
        else:
            t, off, src = dt, None, k + " (no offset: assumed UTC per QuickTime spec)"
    if t is None:
        for k, v in d.items():
            if k.endswith("FileModifyDate"):
                dt, o = parse_date(v)
                if dt:
                    t, off, src = (dt - o if o else dt), o, k + " (file mtime: copy time, unreliable)"
    cam = " ".join(str(d.get(k, "")) for k in d if k.endswith((":Make", ":Model")))[:60].strip()
    dur = next((duration_s(v) for k, v in d.items() if k.endswith(":Duration") and duration_s(v) > 0), 0.0)
    return dict(clip=clip, camera=cam or "unknown", t_utc=t, offset=off, time_source=src or "none",
                duration_s=round(dur, 2), points=pts)


rows = [extract(p) for p in sorted(glob.glob(os.path.join(A, "metadata", "*.exiftool.json")))]
if not rows:
    sys.exit("no assets/metadata/*.exiftool.json: run 01_extract_metadata.sh first")
warn = []

# time zone for local dates: explicit per clip > most common offset > --tz-offset > UTC (flagged)
offs = Counter(r["offset"] for r in rows                    # a file mtime's zone is the computer's, not the camera's
               if r["offset"] is not None and not r["time_source"].endswith("unreliable)"))
if TZ_ARG:
    s = TZ_ARG
    trip_off = timedelta(hours=int(s[1:3]), minutes=int(s[4:6])) * (1 if s[0] == "+" else -1)
elif offs:
    trip_off = offs.most_common(1)[0][0]
    if len(offs) > 1:
        warn.append(f"several UTC offsets in clip metadata {[str(o) for o in offs]}: travel across zones, or a camera clock set wrong")
else:
    trip_off = None
    warn.append("no clip carries a UTC offset: local dates use UTC; pass --tz-offset +HH:MM (ask the user or derive from GPS)")
missing_t = [r["clip"] for r in rows if r["t_utc"] is None]
if missing_t:
    warn.append(f"no usable timestamp: {missing_t} (placed at the end; ask the user)")
for r in rows:
    if r["time_source"].endswith("unreliable)") and not re.search(r"(\d{8})[_-]?(\d{6})", r["clip"]):
        warn.append(f"{r['clip']}: time from file mtime only")   # filename-timed clips are fixed below
    r["local"] = (r["t_utc"] + (r["offset"] if r["offset"] is not None else (trip_off or timedelta(0)))) if r["t_utc"] else None
    p = r["points"]
    r["lat"], r["lon"] = (round(p[0][0], 6), round(p[0][1], 6)) if p else ("", "")
    r["gps_source"] = p[0][2] if p else "none"
    # in-clip movement: first vs last distinct point over the clip duration
    r["moving"] = False
    if len(p) >= 2 and r["duration_s"] > 0:
        far = max(haversine(p[0], q) for q in p[1:])
        r["moving"] = far / r["duration_s"] * 3.6 > MOVE_KMH
# filename clock cross-check (cameras without a UTC offset in their metadata). Insta360 (VID_/IMG_/LRV_),
# Samsung (YYYYMMDD_HHMMSS) and DJI (DJI_YYYYMMDDHHMMSS) name files by the camera's LOCAL wall clock.
# Comparing it with the metadata time shows whether CreateDate is really UTC, and which zone the camera's clock is
# set to (e.g. still on home time after a flight). Pixel's PXL_ names are UTC, so they are not used.
FN = re.compile(r"(?:^|[_-])(\d{4})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})")
# mtime-only clips (zeroed metadata dates, e.g. Insta360 app exports such as Flow_VID_...): the filename's local
# wall-clock time beats the copy time, read in the trip's zone
for r in rows:
    m = FN.search(r["clip"])
    if not (r["time_source"].endswith("unreliable)") and m and trip_off is not None):
        continue
    try:
        fn_local = datetime(*map(int, m.groups()))
    except ValueError:
        continue
    r["t_utc"], r["offset"], r["local"] = fn_local - trip_off, trip_off, fn_local
    r["filename_time"] = fn_local.isoformat()
    r["time_source"] = f"filename local time (metadata date zeroed; file mtime ignored) in trip offset {trip_off}"
for r in rows:
    if r["offset"] is not None or r["t_utc"] is None or r["clip"].upper().startswith("PXL_"):
        continue
    m = FN.search(r["clip"])
    if not m:
        continue
    try:
        fn_local = datetime(*map(int, m.groups()))
    except ValueError:
        continue
    implied = fn_local - r["t_utc"]                       # camera clock zone, if CreateDate is true UTC
    mins = round(implied.total_seconds() / 60)
    r["filename_time"] = fn_local.isoformat()
    if abs(mins) <= 2:                                     # CreateDate holds LOCAL time, not UTC
        if trip_off is not None:
            r["t_utc"] = fn_local - trip_off
            r["local"] = fn_local
            r["time_source"] += f" -> camera writes local time; UTC = filename time - trip offset {trip_off}"
        else:
            warn.append(f"{r['clip']}: metadata time equals the filename's local time (camera writes local time, not UTC) "
                        f"and no trip offset is known: pass --tz-offset so it lands on the right day and visit")
    elif mins % 15 == 0 and -12 * 60 <= mins <= 14 * 60:   # a real zone: the camera's clock is set to it
        zone = timedelta(minutes=mins)
        if trip_off is not None and zone != trip_off:
            warn.append(f"{r['clip']}: camera clock is on UTC{'+' if mins >= 0 else '-'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}, "
                        f"the trip's other clips on {trip_off}: its time zone wasn't updated (grouping uses UTC, so it is still "
                        f"placed correctly; update the camera's zone in its app)")
        if trip_off is None:
            r["local"] = fn_local                          # best local guess: the camera's own clock
    else:
        warn.append(f"{r['clip']}: filename time and metadata time differ by {mins} min (not a time zone): "
                    f"camera clock is wrong; ask the user, or correct with the phone clips of the same moment")
no_gps = [r["clip"] for r in rows if not r["points"]]
if no_gps:
    warn.append(f"{len(no_gps)}/{len(rows)} clips have no GPS (e.g. Insta360 Studio exports): grouped by time + visuals; "
                f"borrow location from the nearest phone clip only if it is within the same visit")

rows.sort(key=lambda r: (r["t_utc"] is None, r["t_utc"] or datetime.max))

# per-camera clock sanity: a camera whose clips all sit far from the others' timeline is suspicious
cams = {}
for r in rows:
    if r["t_utc"]:
        cams.setdefault(r["camera"], []).append(r["t_utc"])
if len(cams) > 1:
    spans = {c: (min(v), max(v)) for c, v in cams.items()}
    for c, (a, b) in spans.items():
        others = [s for k, s in spans.items() if k != c]
        if all(b < oa - timedelta(hours=2) or a > ob + timedelta(hours=2) for oa, ob in others):
            warn.append(f"camera '{c}' clips don't overlap the other cameras' time span: check its clock / time zone")

# ---------- group into visits ----------
visits, cur = [], None
prev = None
for r in rows:
    new = cur is None
    transit_gap = False
    if prev is not None and r["t_utc"] and prev["t_utc"]:
        gap_s = (r["t_utc"] - (prev["t_utc"] + timedelta(seconds=prev["duration_s"]))).total_seconds()
        dist = haversine(prev["points"][0], r["points"][0]) if prev["points"] and r["points"] else None
        speed = (dist / max(gap_s, 1) * 3.6) if dist is not None else None
        if gap_s > GAP_MIN * 60 or (dist is not None and dist > DIST_M):
            new = True
            transit_gap = speed is not None and speed > MOVE_KMH
        if r["local"] and prev["local"] and r["local"].date() != prev["local"].date():
            new = True
    # movement known only with in-clip GPS; a clip without GPS joins the current visit when close in time
    kind = ("transit" if r["moving"] else "stop") if len(r["points"]) >= 2 else ("stop" if r["points"] else None)
    if cur is not None and not new and kind is not None and cur["kind"] not in (kind, "unknown"):
        new = True
    if cur is not None and not new and cur["kind"] == "unknown" and kind is not None:
        cur["kind"] = kind                       # first clip with evidence decides
    if new:
        cur = dict(kind=kind or "unknown", clips=[], gap_before="transit" if transit_gap else "")
        visits.append(cur)
    cur["clips"].append(r)
    prev = r

types = {}
for cand in (os.path.join(A, "visit_types.json"), os.path.join(os.path.dirname(ROOT), "visit_types.json"),
             os.path.expanduser("~/.claude/skills/travel-reel/visit_types.json")):
    if os.path.exists(cand):
        types = json.load(open(cand)).get("types", {}); break


def osm_to_type(cat, typ):
    for name, t in types.items():
        for tag in t.get("osm", []):
            c, _, ty = tag.partition(":")
            if c == cat and (ty == "*" or ty == typ):
                return name
    return ""


cache_p = os.path.join(A, "geocode_cache.json")
cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}


def reverse(lat, lon):
    key = f"{lat:.5f},{lon:.5f}"
    if key in cache:
        return cache[key]
    q = urllib.parse.urlencode(dict(lat=lat, lon=lon, format="jsonv2", zoom=18, namedetails=1, addressdetails=1))
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/reverse?{q}",
                                 headers={"User-Agent": "travel-reel-skill/1.0 (personal video editing)",
                                          "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=20) as fh:
            res = json.load(fh)
    except Exception as e:                       # offline / rate-limited: keep going, retry next run
        time.sleep(1.1)
        warn.append(f"geocode failed for {key}: {e} (not cached; re-run with --geocode later)")
        return {}
    time.sleep(1.1)                              # Nominatim usage policy: max 1 request per second
    cache[key] = res
    return res


days = sorted({r["local"].date() for r in rows if r["local"]})
day_no = {d: i + 1 for i, d in enumerate(days)}
vrows, crows = [], []
for i, v in enumerate(visits, 1):
    vid = f"V{i:02d}"
    pts = [r["points"][0] for r in v["clips"] if r["points"]]
    lat = round(sum(p[0] for p in pts) / len(pts), 6) if pts else ""
    lon = round(sum(p[1] for p in pts) / len(pts), 6) if pts else ""
    place = dict(name="", name_local="", osm_category="", osm_type="")
    if GEOCODE and pts and v["kind"] != "transit":
        res = reverse(lat, lon)
        nd = res.get("namedetails") or {}
        place = dict(name=nd.get("name:en") or res.get("name") or "", name_local=nd.get("name") or "",
                     osm_category=res.get("category", ""), osm_type=res.get("type", ""))
    t0 = min((r["local"] for r in v["clips"] if r["local"]), default=None)
    t1 = max((r["local"] + timedelta(seconds=r["duration_s"]) for r in v["clips"] if r["local"]), default=None)
    sugg = "transit" if v["kind"] == "transit" else osm_to_type(place["osm_category"], place["osm_type"])
    vrows.append(dict(visit_id=vid, day=day_no.get(t0.date(), "") if t0 else "", kind=v["kind"],
                      start_local=t0.isoformat(timespec="minutes") if t0 else "",
                      end_local=t1.isoformat(timespec="minutes") if t1 else "",
                      n_clips=len(v["clips"]), seconds=round(sum(r["duration_s"] for r in v["clips"]), 1),
                      clips=" ".join(r["clip"] for r in v["clips"]), lat=lat, lon=lon,
                      place_name=place["name"], place_name_local=place["name_local"],
                      osm=f"{place['osm_category']}:{place['osm_type']}".strip(":"),
                      suggested_type=sugg, type="", type_evidence="", location_mode=""))
    for r in v["clips"]:
        crows.append(dict(clip=r["clip"], camera=r["camera"], visit_id=vid,
                          day=day_no.get(r["local"].date(), "") if r["local"] else "",
                          start_local=r["local"].isoformat(timespec="seconds") if r["local"] else "",
                          time_source=r["time_source"], duration_s=r["duration_s"], lat=r["lat"], lon=r["lon"],
                          gps_source=r["gps_source"], moving=r["moving"]))

if GEOCODE:
    json.dump(cache, open(cache_p, "w"), indent=1, ensure_ascii=False)

stops = [v for v in vrows if v["kind"] == "stop"]
unknown = [v for v in vrows if v["kind"] == "unknown"]
transits = [v for v in vrows if v["kind"] == "transit"] + [v for v, raw in zip(vrows, visits) if raw["gap_before"]]
places = len(stops) + len(unknown)          # 'unknown' = no GPS: a place or a ride, judged from the footage
if len(days) > 1:
    tier = "multi-day"
elif len(vrows) == 1:
    tier = "single-visit"
elif transits and places <= 2:
    tier = "ride-and-stop"
else:
    tier = "day-trip"
if unknown and len(vrows) > 1:
    warn.append(f"{len(unknown)} of {len(vrows)} visits have no GPS ('unknown'): tier '{tier}' is from time gaps only; "
                f"confirm from the contact sheets (a ride with no GPS looks like a separate visit)")

os.makedirs(A, exist_ok=True)
for name, data in (("catalogue.csv", crows), ("visits.csv", vrows)):
    with open(os.path.join(A, name), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
scope = dict(tier=tier, days=len(days), clips=len(rows), visits=len(vrows), stops=len(stops), unknown_visits=len(unknown),
             transit_legs=len([v for v in vrows if v["kind"] == "transit"]),
             transit_gaps=len([1 for raw in visits if raw["gap_before"]]),
             trip_utc_offset=str(trip_off) if trip_off is not None else None,
             thresholds=dict(gap_min=GAP_MIN, dist_m=DIST_M, move_kmh=MOVE_KMH), warnings=warn)
json.dump(scope, open(os.path.join(A, "scope.json"), "w"), indent=1)
print(json.dumps(scope, indent=1))
for v in vrows:
    print(f"{v['visit_id']} day {v['day']} {v['kind']:7s} {v['start_local'][11:]}-{v['end_local'][11:]} "
          f"{v['n_clips']} clips  {v['place_name'] or '-'}  suggested={v['suggested_type'] or '?'}")
