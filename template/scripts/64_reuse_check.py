"""Cross-reel caption check: a clip may be reused in several reels, but the text over it must not repeat.
(Jpn trip: the night-train clip closed both reels with near-identical captions, "Same line, after dark 🌙"
and "And it glows after dark 🌙"; the user asked for reused clips to carry different captions.)

Run from the PROJECT root (multi-reel: checks every reels/*/ plus the root's own cut; single reel: checks
the root, where a clip used for two shots counts too). For every pair of shots that use the same source clip,
it collects the on-screen text shown over each shot (assets/overlays.csv captions + kickers, and the text
values of assets/motion_plan.json graphics) and flags pairs whose text repeats:
  - same emoji, or
  - a shared content word pair (bigram, stop words removed), e.g. "after dark", or
  - word overlap (Jaccard on content words) >= 0.34, or difflib ratio >= 0.6.
Reusing a clip is fine; reusing its caption idea is not: rewrite one of them from a different angle
(a fact, the journey, a feeling) rather than rephrasing it.

Usage: 64_reuse_check.py [--strict]    (--strict exits 1 when anything is flagged)
Output: assets/reuse_check.json + a printed list of flagged pairs."""
import csv, difflib, glob, json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT

STOP = set("a an the and or but of on in at to for from with by it its is are was were be this that these those my our "
           "your we i you he she they them me us so just very all some into onto over under up down out off again here "
           "there then than too also same".split())
TEXT_KEYS = ("title", "kicker", "subtitle", "line1", "line2", "keyword", "label", "text")


def projects():
    reels = sorted(d for d in glob.glob(os.path.join(ROOT, "reels", "*")) if os.path.exists(os.path.join(d, "assets", "edl.csv")))
    own = [ROOT] if os.path.exists(os.path.join(ROOT, "assets", "edl.csv")) else []
    return own + reels


def shots(proj):
    out, t = [], 0.0
    for r in csv.DictReader(open(os.path.join(proj, "assets", "edl.csv"), encoding="utf-8")):
        d = float(r["dur"])
        out.append(dict(id=r["id"], clip=r["clip"], tin=float(r["tin"]), t0=t, t1=t + d))
        t += d
    return out


def texts(proj):
    """(t_in, t_out, text) for every caption and motion graphic in the reel."""
    out = []
    p = os.path.join(proj, "assets", "overlays.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            s = " ".join(x for x in (r.get("kicker"), r.get("text")) if x)
            out.append((float(r["t_in"]), float(r["t_out"]), s.strip(), "caption"))
    p = os.path.join(proj, "assets", "motion_plan.json")
    if os.path.exists(p):
        for g in json.load(open(p, encoding="utf-8")):
            vals = g.get("set", {})
            s = " ".join(str(vals[k]) for k in TEXT_KEYS if vals.get(k))
            dur = g.get("duration") or template_duration(g.get("template", ""), proj)
            if s:
                out.append((float(g["start"]), float(g["start"]) + dur, s, "graphic:" + g.get("template", g.get("id", ""))))
    return out


SKILL = os.environ.get("TRAVEL_REEL_SKILL", os.path.expanduser("~/.claude/skills/travel-reel"))


def template_duration(name, proj):
    """data-duration of the motion template (project copy first, as 70_motion.py); 3.5 s if not found."""
    for d in (os.path.join(proj, "motion", "templates"), os.path.join(ROOT, "motion", "templates"),
              os.path.join(SKILL, "template", "motion", "templates")):
        p = os.path.join(d, name + ".html")
        if os.path.exists(p):
            m = re.search(r'data-composition-id="main"[^>]*data-duration="([\d.]+)"', open(p, encoding="utf-8").read())
            if m:
                return float(m.group(1))
    return 3.5


def emoji(s):
    return {c for c in s if unicodedata.category(c) == "So"}


def words(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'-]*", s) if w not in STOP]


def compare(a, b):
    why = []
    e = emoji(a) & emoji(b)
    if e:
        why.append("same emoji " + "".join(sorted(e)))
    wa, wb = words(a), words(b)
    bi = {tuple(wa[i:i + 2]) for i in range(len(wa) - 1)} & {tuple(wb[i:i + 2]) for i in range(len(wb) - 1)}
    if bi:
        why.append("shared phrase " + ", ".join('"' + " ".join(x) + '"' for x in sorted(bi)))
    sa, sb = set(wa), set(wb)
    j = len(sa & sb) / len(sa | sb) if sa | sb else 0.0
    if j >= 0.34:
        why.append(f"word overlap {j:.2f} ({', '.join(sorted(sa & sb))})")
    r = difflib.SequenceMatcher(None, " ".join(wa), " ".join(wb)).ratio()
    if r >= 0.6:
        why.append(f"similar wording {r:.2f}")
    return why


items = []
for proj in projects():
    name = os.path.relpath(proj, ROOT) if proj != ROOT else "."
    tx = texts(proj)
    for s in shots(proj):
        over = [t for t in tx if t[0] < s["t1"] and t[1] > s["t0"]]
        items.append(dict(reel=name, shot=s["id"], clip=s["clip"], texts=over))

flags = []
for i, a in enumerate(items):
    for b in items[i + 1:]:
        if a["clip"] != b["clip"] or a["clip"].startswith("(") or not a["texts"] or not b["texts"]:
            continue
        for ta in a["texts"]:
            for tb in b["texts"]:
                if ta is tb:
                    continue                                        # one caption spanning two shots of the same clip
                why = compare(ta[2], tb[2])
                if why:
                    flags.append(dict(clip=a["clip"], a=f'{a["reel"]}/{a["shot"]}', a_text=ta[2], a_kind=ta[3],
                                      b=f'{b["reel"]}/{b["shot"]}', b_text=tb[2], b_kind=tb[3], why=why))

reused = sorted({(x["clip"]) for x in items if sum(y["clip"] == x["clip"] for y in items) > 1 and not x["clip"].startswith("(")})
json.dump(dict(reused_clips=reused, flagged=flags), open(os.path.join(ROOT, "assets", "reuse_check.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"{len(reused)} clip(s) used more than once: {', '.join(reused) or 'none'}")
for f in flags:
    print(f'FLAG {f["clip"]}: {f["a"]} "{f["a_text"]}"  vs  {f["b"]} "{f["b_text"]}"  -> {"; ".join(f["why"])}')
print(f"{len(flags)} repeated caption pair(s)" if flags else "no repeated captions on reused clips")
sys.exit(1 if flags and "--strict" in sys.argv else 0)
