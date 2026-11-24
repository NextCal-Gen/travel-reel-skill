"""Review page: ONE local HTML file to review rough cuts on a laptop or phone, then send changes back as text.

Usage: 63_review_page.py [--video previews/rough_cut_vN.mp4] [--all]
  default: this project's latest previews/rough_cut_v*.mp4
  --all:   every reel in reels/*/ (multi-reel projects) on one page, plus this folder's own cut if any
Writes previews/review.html (+ previews/review_assets/ thumbnails). Open it in a browser; nothing is uploaded.

On the page: each reel plays inside a phone frame with the Instagram safe zone (toggle), a timeline of shots,
captions and graphics; click any item (or "note at current time"), type what should change, then "Copy
instructions" and paste the text back to Claude. Notes are kept in the browser (localStorage) until cleared.
Shot times come from work/shots/<id>.mov frame counts (as 60_assemble), captions from assets/overlays.csv,
graphics from assets/motion_plan.json."""
import csv, glob, html, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from lib_reel import ROOT
from lib_safe import W, H, SAFE

FPS = 30
PREV = os.path.join(ROOT, "previews")
TH = os.path.join(PREV, "review_assets")


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def nframes(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    return int(r) if r.isdigit() else 0


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True).stdout.strip()
    try:
        return float(r)
    except ValueError:
        return 0.0


def latest_cut(root):
    vids = glob.glob(os.path.join(root, "previews", "rough_cut_v*.mp4"))
    key = lambda p: [int(x) for x in re.findall(r"\d+", os.path.basename(p))] or [0]
    return max(vids, key=key) if vids else None


def reel_data(root, video, name):
    items, t = [], 0.0
    edl = os.path.join(root, "assets", "edl.csv")
    if os.path.exists(edl):
        for r in csv.DictReader(open(edl, encoding="utf-8")):
            shot = os.path.join(root, "work", "shots", f"{r['id']}.mov")
            d = nframes(shot) / FPS if os.path.exists(shot) else float(r.get("dur") or 0)
            items.append(dict(kind="shot", id=r["id"], t0=round(t, 2), t1=round(t + d, 2),
                              text=f"{r.get('role', '')} · {os.path.basename(r.get('clip', ''))} {float(r.get('tin') or 0):.1f}-{float(r.get('tout') or 0):.1f}s"))
            t += d
    ov = os.path.join(root, "assets", "overlays.csv")
    if os.path.exists(ov):
        for i, r in enumerate(csv.DictReader(open(ov, encoding="utf-8")), 1):
            items.append(dict(kind="caption", id=f"C{i:02d}", t0=float(r["t_in"]), t1=float(r["t_out"]),
                              text=f"[{r.get('style', '')}] {r.get('text', '')}"))
    mp = os.path.join(root, "assets", "motion_plan.json")
    if os.path.exists(mp):
        for g in json.load(open(mp, encoding="utf-8")):
            mov = os.path.join(root, "work", "motion", g["id"] + ".mov")
            rep = os.path.join(root, "work", "motion", g["id"] + ".json")
            d = duration(mov) if os.path.exists(mov) else 3.0
            tpl = json.load(open(rep, encoding="utf-8")).get("template", "") if os.path.exists(rep) else ""
            items.append(dict(kind="graphic", id=g["id"], t0=float(g["start"]), t1=round(float(g["start"]) + d, 2),
                              text=f"{tpl or 'graphic'}"))
    # one thumbnail per shot from the cut itself (what the viewer sees)
    os.makedirs(TH, exist_ok=True)
    for it in items:
        if it["kind"] != "shot":
            continue
        tp = os.path.join(TH, f"{name}_{it['id']}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(it['t0'] + it['t1']) / 2:.2f}", "-i", video,
                        "-frames:v", "1", "-vf", "scale=120:-2", "-q:v", "5", tp], check=False)
        it["thumb"] = os.path.relpath(tp, PREV)
    return dict(name=name, video=os.path.relpath(video, PREV), duration=round(duration(video), 2),
                items=sorted(items, key=lambda x: (x["t0"], x["kind"])),
                cutcheck=os.path.relpath(os.path.join(root, "assets", "cut_check.jpg"), PREV)
                if os.path.exists(os.path.join(root, "assets", "cut_check.jpg")) else None)


reels = []
if "--all" in sys.argv:
    own = latest_cut(ROOT)
    if own:
        reels.append(reel_data(ROOT, own, os.path.basename(ROOT)))
    for rd in sorted(glob.glob(os.path.join(ROOT, "reels", "*"))):
        v = latest_cut(rd)
        if v:
            reels.append(reel_data(rd, v, os.path.basename(rd)))
else:
    v = arg("--video")
    v = (v if os.path.isabs(v) else os.path.join(ROOT, v)) if v else latest_cut(ROOT)
    if not v:
        sys.exit("no previews/rough_cut_v*.mp4 (or pass --video)")
    reels.append(reel_data(ROOT, v, os.path.basename(ROOT)))
if not reels:
    sys.exit("no rough cuts found")

safe = dict(top=SAFE["top"] / H, bottom=SAFE["bottom"] / H, left=SAFE["left"] / W, right=SAFE["right"] / W,
            btn_top=SAFE["btn_top"] / H, btn_right=SAFE["btn_right"] / W)
page = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review</title><style>
:root{--bg:#f6f3ee;--fg:#1f1b16;--mut:#7b7268;--card:#fff;--line:#e4ddd3;--acc:#c8871c;--shot:#7fa3c9;--cap:#d9a441;--gfx:#9b7fd1}
@media (prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f1ece4;--mut:#a39a8f;--card:#211e1b;--line:#38332d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}
header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:5}
header h1{font-size:17px;margin:0 8px 0 0}button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:6px 12px;cursor:pointer}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff}.reel{display:grid;grid-template-columns:minmax(260px,340px) 1fr;gap:20px;padding:18px;border-bottom:1px solid var(--line)}
@media (max-width:760px){.reel{grid-template-columns:1fr}}
.phone{position:relative;aspect-ratio:9/16;background:#000;border-radius:28px;overflow:hidden;border:8px solid #111;max-width:340px}
.phone video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.safe{position:absolute;inset:0;pointer-events:none}.safe div{position:absolute;background:rgba(255,40,40,.18)}
.tl{position:relative;height:46px;margin:10px 0 4px;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;cursor:pointer}
.seg{position:absolute;height:14px;border-radius:3px;opacity:.85}.ph{position:absolute;top:0;bottom:0;width:2px;background:var(--fg)}
.list{max-height:70vh;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.it{display:grid;grid-template-columns:64px 1fr;gap:10px;padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer}
.it:hover{background:rgba(200,135,28,.08)}.it img{width:64px;border-radius:4px}.tag{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.k-shot{color:var(--shot)}.k-caption{color:var(--cap)}.k-graphic{color:var(--gfx)}.mut{color:var(--mut);font-size:13px}
textarea{width:100%;margin-top:6px;font:inherit;border:1px solid var(--line);border-radius:6px;padding:6px;background:var(--bg);color:var(--fg)}
.has{box-shadow:inset 3px 0 0 var(--acc)}.legend span{margin-right:12px;font-size:12px}
</style></head><body>
<header><h1>Rough-cut review</h1><button class="pri" id="copy">Copy instructions</button><button id="safeT">Safe zone on/off</button>
<button id="clear">Clear notes</button><span class="mut" id="msg"></span></header>
<div id="app"></div>
<script>
var DATA = __DATA__, SAFE = __SAFE__;
var KEY = 'review:' + location.pathname, notes = {};
try { notes = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { notes = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(notes)); } catch (e) {} }
function fmt(t) { var m = Math.floor(t / 60), s = (t - m * 60).toFixed(1); return (m ? m + ':' : '') + (s < 10 && m ? '0' : '') + s + 's'; }
function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
var app = document.getElementById('app'), showSafe = true;
DATA.forEach(function (R, ri) {
  var el = document.createElement('section'); el.className = 'reel';
  var segs = R.items.map(function (it) {
    var row = it.kind === 'shot' ? 4 : it.kind === 'caption' ? 18 : 32;
    return '<div class="seg" title="' + esc(it.id + ' ' + it.text) + '" style="top:' + row + 'px;left:' + (100 * it.t0 / R.duration) + '%;width:' +
      Math.max(0.6, 100 * (it.t1 - it.t0) / R.duration) + '%;background:var(--' + (it.kind === 'shot' ? 'shot' : it.kind === 'caption' ? 'cap' : 'gfx') + ')"></div>';
  }).join('');
  var list = R.items.map(function (it, i) {
    var k = R.name + '|' + it.kind + '|' + it.id;
    return '<div class="it' + (notes[k] ? ' has' : '') + '" data-i="' + i + '">' + (it.thumb ? '<img src="' + esc(it.thumb) + '">' : '<div></div>') +
      '<div><span class="tag k-' + it.kind + '">' + it.kind + ' ' + esc(it.id) + '</span> <span class="mut">' + fmt(it.t0) + '–' + fmt(it.t1) + '</span><br>' + esc(it.text) +
      '<textarea rows="2" placeholder="What should change?" data-k="' + esc(k) + '">' + esc(notes[k] || '') + '</textarea></div></div>';
  }).join('');
  el.innerHTML = '<div><div class="phone"><video src="' + esc(R.video) + '" controls playsinline preload="metadata"></video><div class="safe"></div></div>' +
    '<div class="tl">' + segs + '<div class="ph"></div></div><div class="legend mut"><span style="color:var(--shot)">■ shots</span><span style="color:var(--cap)">■ captions</span><span style="color:var(--gfx)">■ graphics</span></div>' +
    '<p><button data-now="1">Note at current time</button></p><div class="now"></div>' +
    (R.cutcheck ? '<p><a href="' + esc(R.cutcheck) + '" target="_blank">Cut check sheet</a></p>' : '') + '</div>' +
    '<div><h2 style="margin:0 0 8px;font-size:16px">' + esc(R.name) + ' <span class="mut">' + fmt(R.duration) + '</span></h2><div class="list">' + list + '</div></div>';
  app.appendChild(el);
  var vid = el.querySelector('video'), tl = el.querySelector('.tl'), ph = el.querySelector('.ph'), sf = el.querySelector('.safe');
  sf.innerHTML = '<div style="left:0;right:0;top:0;height:' + SAFE.top * 100 + '%"></div><div style="left:0;right:0;bottom:0;height:' + (1 - SAFE.bottom) * 100 + '%"></div>' +
    '<div style="left:' + SAFE.btn_right * 100 + '%;right:0;top:' + SAFE.btn_top * 100 + '%;bottom:' + (1 - SAFE.bottom) * 100 + '%"></div>';
  vid.addEventListener('timeupdate', function () { ph.style.left = (100 * vid.currentTime / (vid.duration || R.duration)) + '%'; });
  tl.addEventListener('click', function (e) { var r = tl.getBoundingClientRect(); vid.currentTime = (e.clientX - r.left) / r.width * (vid.duration || R.duration); });
  el.querySelectorAll('.it').forEach(function (row) {
    row.addEventListener('click', function (e) { if (e.target.tagName !== 'TEXTAREA') { vid.currentTime = R.items[+row.dataset.i].t0 + 0.05; vid.pause(); } });
  });
  el.addEventListener('input', function (e) {
    if (e.target.dataset.k) { var k = e.target.dataset.k; if (e.target.value.trim()) notes[k] = e.target.value; else delete notes[k]; save();
      var row = e.target.closest('.it'); if (row) row.classList.toggle('has', !!notes[k]); }
  });
  el.querySelector('[data-now]').addEventListener('click', function () {
    var t = vid.currentTime.toFixed(2), k = R.name + '|time|' + t, box = el.querySelector('.now');
    notes[k] = notes[k] || ''; save();
    box.insertAdjacentHTML('beforeend', '<div class="mut">At ' + fmt(+t) + '</div><textarea rows="2" data-k="' + esc(k) + '" placeholder="What should change here?"></textarea>');
    box.lastElementChild.focus();
  });
  Object.keys(notes).forEach(function (k) {
    var p = k.split('|'); if (p[0] !== R.name || p[1] !== 'time') return;
    el.querySelector('.now').insertAdjacentHTML('beforeend', '<div class="mut">At ' + fmt(+p[2]) + '</div><textarea rows="2" data-k="' + esc(k) + '">' + esc(notes[k]) + '</textarea>');
  });
});
document.getElementById('safeT').onclick = function () { showSafe = !showSafe; document.querySelectorAll('.safe').forEach(function (s) { s.style.display = showSafe ? '' : 'none'; }); };
document.getElementById('clear').onclick = function () { if (confirm('Clear all notes on this page?')) { notes = {}; save(); location.reload(); } };
document.getElementById('copy').onclick = function () {
  var out = [];
  DATA.forEach(function (R) {
    var lines = [];
    R.items.forEach(function (it) { var n = notes[R.name + '|' + it.kind + '|' + it.id]; if (n && n.trim())
      lines.push('- ' + it.kind + ' ' + it.id + ' (' + fmt(it.t0) + '–' + fmt(it.t1) + ', ' + it.text + '): ' + n.trim()); });
    Object.keys(notes).forEach(function (k) { var p = k.split('|'); if (p[0] === R.name && p[1] === 'time' && notes[k].trim())
      lines.push('- at ' + fmt(+p[2]) + ': ' + notes[k].trim()); });
    if (lines.length) out.push('Reel ' + R.name + ' (' + R.video + '):\n' + lines.join('\n'));
  });
  var text = out.length ? 'Review comments on the rough cut(s). Apply these, re-render, and show me the new cut:\n\n' + out.join('\n\n') : '';
  var msg = document.getElementById('msg');
  if (!text) { msg.textContent = 'No notes yet.'; return; }
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { msg.textContent = 'Copied. Paste it to Claude.'; },
    function () { window.prompt('Copy this and paste it to Claude:', text); });
};
</script></body></html>"""
out = os.path.join(PREV, "review.html")
os.makedirs(PREV, exist_ok=True)
open(out, "w", encoding="utf-8").write(page.replace("__DATA__", json.dumps(reels, ensure_ascii=False)).replace("__SAFE__", json.dumps(safe)))
print(out, f"({len(reels)} reel{'s' if len(reels) != 1 else ''}, {sum(len(r['items']) for r in reels)} items)")
