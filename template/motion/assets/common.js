/* Shared helpers for travel-reel motion templates (1080x1920 transparent overlays).
   Safe zone = Instagram Reels UI: nothing above y 220 or below y 1470, 70 px side margins,
   and nothing right of x 980 below y 1155 (like / comment / share buttons).
   Same numbers as scripts/lib_safe.py; 70_motion.py verifies every render against them. */
window.TR = (function () {
  var W = 1080, H = 1920;
  var SAFE = { top: 220, bottom: 1470, left: 70, right: 1010, btnTop: 1155, btnRight: 980 };
  function vars() {
    var hf = window.__hyperframes;
    return hf && hf.getVariables ? hf.getVariables() : {};
  }
  function json(v, d) {
    if (v === undefined || v === null || v === '') return d;
    if (typeof v !== 'string') return v;
    try { return JSON.parse(v); } catch (e) { return d; }
  }
  function num(v, d) { var n = parseFloat(v); return isFinite(n) ? n : d; }
  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  /* keep a w x h box inside the safe zone, including the button column */
  function clampBox(x, y, w, h) {
    x = Math.max(SAFE.left, Math.min(x, SAFE.right - w));
    y = Math.max(SAFE.top, Math.min(y, SAFE.bottom - h));
    if (y + h > SAFE.btnTop) x = Math.max(SAFE.left, Math.min(x, SAFE.btnRight - w));
    return { x: x, y: y };
  }
  /* vertical anchors: content top for top/upper/center, content bottom for lower */
  var POS = { top: 260, upper: 520, center: 820, lower: 1180 };
  function place(el, pos) {
    /* lower: content bottom sits 40 px above the line, leaving room for entry/exit motion */
    if (pos === 'lower') { el.style.bottom = (H - SAFE.bottom + 40) + 'px'; el.style.top = 'auto'; }
    else { el.style.top = (POS[pos] || POS.center) + 'px'; }
  }
  return { W: W, H: H, SAFE: SAFE, vars: vars, json: json, num: num, esc: esc, clampBox: clampBox,
           POS: POS, place: place };
})();
