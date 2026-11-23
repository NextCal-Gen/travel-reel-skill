# Multi-reel planning (Phase P)

Read this when `assets/scope.json` says the project holds more than one visit, or when the user
asks for several reels from one batch of clips. Generic: a single cafe visit, a ride + stop, a day
trip and a multi-day trip all use the same steps; only the proposed menu changes.

## P.1 Catalogue (always, right after Phase 1; cheap)

`07_catalogue.py` (add `--geocode` when GPS exists; it sends visit coordinates to OSM Nominatim,
1 request/s, cached) → `assets/catalogue.csv`, `assets/visits.csv`, `assets/scope.json`.

- **Visits** split on a time gap (> 20 min), a distance gap (> 300 m) or a new local date. **Kind**:
  `transit` (GPS moves within the clip), `stop` (GPS stationary) or `unknown` (no GPS; you decide
  from the footage). Thresholds are starting values: re-run with `--gap-min/--dist-m/--move-kmh` if
  visits are clearly split or merged wrongly, and say so.
- **Warnings in scope.json are blocking until resolved**: several UTC offsets, a camera whose
  clock doesn't overlap the others, no offset at all (ask for `--tz-offset` or derive it from GPS),
  clips with no timestamp. Wrong clocks put clips in the wrong visit and the wrong day.
- **Clips without GPS** (Insta360 Studio exports) are grouped by time. Borrow a location from a
  phone clip only inside the same visit, and mark it borrowed. Their visits are `unknown` but still
  count toward the tier (several time-separated visits = not single-visit); scope.json warns, and you
  confirm the tier from the contact sheets (a GPS-less ride shows up as its own short visit).
- **Time zones**: iPhone dates carry the offset; Samsung/Android stores it separately
  (`AndroidTimeZone`, read automatically); Insta360 clocks have none, so they take the trip's offset.
- **Single visit** → skip the rest of this file and run the normal workflow at the project root.

## P.2 Label visits (look, don't guess)

For each visit, build a contact sheet from its clips (`03_contact_sheets.py` on those clips) and view it.
Fill `type` in `assets/visits.csv` from `visit_types.json` (stay, cafe, food, nature, heritage,
market, transit, other, or a type the user added), with `type_evidence`:
OSM category, what you saw, and the user's note. Signals agree → set it. Signals disagree, or the
visit is `unknown` and the footage is ambiguous → ask (in the menu round, not separately).
Use the user's own names for places and moments (`notes/dayNN.md` or kickoff answers) over OSM names.

## P.3 Reel menu (one round of questions; skipped on full autopilot)

Propose reels from the tier in `scope.json`. Each proposal: id, kind, visits/clips used, target
duration, opener idea, location mode default, and a one-line reason. The user picks, edits or adds.

| Tier | Default proposals |
|---|---|
| single-visit | 1 reel (normal workflow) + variants |
| ride-and-stop | ride reel (POV highlights), destination reel, combined "ride → stop" reel (route map if chosen) |
| day-trip | one reel per strong visit, day-journey reel (chronological, morning → night), transit reel if the ride is good |
| multi-day | the day-trip set per day, plus at the end: category series (e.g. all cafes), city/region reels, trip trailer |

- **Durations**: place reel 15–20 s, journey/combined 18–25 s (≤ 30 s with a map), trailer ≤ 30 s.
  Pass the reel's range to QC: `61_qc.py <file> --target MIN MAX`.
- **Variants** (cheap: shots already rendered): second hook, 15 s Stories cut, 4:5 carousel stills.
  Offer, don't make by default.
- **Clip reuse**: a hero shot may appear in a place reel and in a journey/series reel, never twice
  in one reel. Don't propose a reel that would mostly repeat another.
- **Weak visits** (few usable seconds, soft or shaky footage) are folded into a journey reel, not
  given their own reel. Say which and why.
- **Standing menu defaults** per tier in the personal defaults file (e.g. "ride-and-stop: combined
  reel + ride POV, no stay reel") are applied without asking; propose only what they don't cover.

## P.4 Location mode (per reel)

Ask per reel in the menu round: **show** (name on screen, map labels) / **hide + comment CTA**
(no name anywhere; CTA asks to comment a keyword or DM; ask the keyword once per project) /
**tag only** (nothing on screen; the user adds Instagram's location tag).

- Defaults come from `visit_types.json` `location_default`, overridden by the personal defaults
  file. `ask` with no answer = **hide**. **Stay reels are always hide unless the user says show.**
- **Hide must not leak**: no place name in captions, kickers or fact cards, and no identifying facts
  ("oldest cafe in X"); route map without labels and without a recognisable destination (drop it,
  or crop/blur the end area); flag shots with readable signage at the storyboard step (keep, crop
  or drop is the user's call; on autopilot: crop or drop, and log it).
- **DM reply helper** for hidden places: `reels/<id>/assets/location_reply.md` with the place name
  (user's name for it first), `https://www.google.com/maps/search/?api=1&query=<lat>,<lon>` from the
  visit centroid, and one ready-to-paste reply line. Never put this file's content in the reel.
- GPS metadata is stripped from every render (`-map_metadata -1`) and QC fails if any survives.

## P.5 Autopilot

Set at kickoff (`Autopilot:` config line or the kickoff question). There is no answer timeout:
a question in Claude Code waits forever, so autopilot works by asking everything first.

| Level | Stops at | Unasked decisions |
|---|---|---|
| off | every gate | asked |
| rough-cuts (default when on) | the review board of all rough cuts; finals wait for approval | safe default, logged |
| finals (opt-in per project) | nothing; finals exported from originals, reviewed afterwards | safe default, logged |

- **Full autopilot skips P.3** only if the kickoff said "menu: auto"; then use the tier defaults and
  standing menu defaults.
- **Safe defaults**: location → hide; ambiguous visit type → `other` (folded into a journey reel);
  low-confidence clip (Gate 1) → excluded from reels and listed; signage in a hidden reel → crop or
  drop. Holder-check hits are never auto-edited: they go on the review board as timestamps.
- Log every autonomous decision in `assets/autopilot_log.md` (what, why, which reel) and lead the
  final summary with it.
- Unattended runs need the permission allowlist (`.claude/settings.json`, copied by `--init-project`)
  and an awake Mac: run long batches under `caffeinate -i`.
- Hard rules still hold: never invent facts, never apply unconfirmed Log transforms, the camera
  holder never appears.

## P.6 Per-reel projects

`bootstrap.sh --init-reel <project> <reel_id>` creates `reels/<reel_id>/` as a normal project
(scripts, folders, looks) sharing the parent's `raw/`, `assets/metadata/`,
`assets/source_inventory.csv` and `work/proxies/` through symlinks, so Phase 1 and proxies run once.
Write the reel's decisions to `reels/<reel_id>/reel.md` (visits, clips, duration, location mode,
text, extras, opener) and run Phases 3–12 inside that folder. One look for the whole project.

## P.7 Batch review

One board for all rough cuts (`assets/review_board.jpg`: per reel, a strip of first/mid/last frames
of each shot, plus duration and location mode) and one message listing every reel's QC result,
holder-check timestamps and autopilot decisions. The user approves or comments per reel in one reply.

## P.8 Cross-day reels (multi-day, after the last day)

Series, city and trailer reels are built from `assets/visits.csv` across days. Pick shots by role
and quality from the per-reel EDLs and shot sheets already made; re-render only new framings.
Keep one caption style per series (e.g. "Day 3/14") when on-screen text is chosen.

## Shot checklists (share with the user before a trip when asked)

- **Stay**: exterior → entrance → walk-in room reveal → window view → details → bathroom.
- **Cafe/food**: sign or storefront → interior → drink or dish being made → close-up → seat with a view.
- **Nature/heritage**: wide establishing → walking approach → textures and details → 5 s static hero.
- **Ride/transit**: mount POV → overtakes or bends → scenery pans → arrival.
- **Every stop**: one phone clip (carries GPS) and a 5–10 s note of names and moments in `notes/dayNN.md`.
