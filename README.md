# travel-reel: Claude Code skill

Raw travel clips (Insta360 360°, iPhone, Samsung, DJI) in → cinematic 9:16 Instagram Reel out.
This repo **is** the skill folder: clone it to `~/.claude/skills/travel-reel` and run `/travel-reel`
in Claude Code from a trip folder.

| File | What |
|---|---|
| `SKILL.md` | The workflow Claude follows (phases, gates, defaults, verified pitfalls) |
| `bootstrap.sh` | Checks/creates the shared toolkit; sets up new trip folders |
| `CLAUDE.template.md` | Per-trip `CLAUDE.md` (kickoff questions, caption rules, hard rules); public and generic |
| `defaults/owner.defaults.md` | The repo owner's standing defaults (who holds the camera, look, opener, Gate 1). `--use-defaults owner` copies it to `~/.claude/travel-reel.defaults.md`, which `--init-project` merges into each new trip's `CLAUDE.md` (a `## Config overrides` section sets config lines such as `- Gate 1 auto-continue: yes`). Other users: skip it, or add `defaults/<you>.defaults.md`. |
| `template/scripts/` | The tested pipeline (see `template/README.md` for run order + what to edit per trip) |
| `template/looks/` | Standing look (Look 2 "warm cinematic") + Insta360/Samsung camera-match LUTs |
| `requirements-*.lock` | Exact Python package versions for the shared toolkit |
| `references/planning.md` | Multi-reel mode: visits from time + GPS, reel menu per tier, per-reel location show/hide, autopilot |
| `visit_types.json` | Editable visit types and OSM tag mapping (copied into each project's `assets/`) |
| `template/settings.json` | Permission allowlist for unattended runs (copied to each project's `.claude/settings.json`) |
| `template/motion/` | Optional motion graphics: 7 HyperFrames templates (title reveal, verdict card, annotations, info chips, comment CTA, day counter, hop map), shared safe-zone helpers, bundled OFL fonts (licences included) |

## Setup on a new Mac (Apple silicon)

Quickest: open Claude Code anywhere and paste
`Install this skill for me: https://github.com/NextCal-Gen/travel-reel-skill`.
It clones the repo into `~/.claude/skills/travel-reel`; then run `/travel-reel` in a trip folder.

Or by hand:

1. Install Claude Code and sign in; install [Homebrew](https://brew.sh) (it asks for your password).
2. Clone this repo into the skills folder (public, no login needed):
   ```bash
   git clone https://github.com/NextCal-Gen/travel-reel-skill.git ~/.claude/skills/travel-reel
   ```
3. Make a trip folder, put your clips in it, open Claude Code there and run `/travel-reel`.
   Phase 0 does the rest after one yes from you: system tools (`bootstrap.sh --install-system`,
   about 30–40 min, mostly the ffmpeg build), the shared toolkit in `~/travel-reel-toolkit`
   (`--create`, about 2 GB), your personal defaults (`--use-defaults owner`), the trip folder
   (`--init-project .`) and moving loose clips into `raw/`.

Manual equivalent: `bootstrap.sh --install-system`, `--create`, `--use-defaults owner`, `--check`.
Motion graphics (optional, about 300 MB): `--install-system --with-motion` (Node 22+, only if missing),
then `--create --with-motion`. Phase 0 offers this when you pick motion graphics at kickoff.

## New trip

```bash
~/.claude/skills/travel-reel/bootstrap.sh --init-project ~/Desktop/my-trip
```
Creates:
```
my-trip/
├── CLAUDE.md            ← set the trip name; your standing defaults (if the defaults file exists) + kickoff questions
├── raw/                 ← put original clips here (read-only)
├── references/look/
├── luts/                ← official manufacturer LUTs only
├── assets/looks/        ← standing look + camera-match LUTs
├── assets/map/
├── scripts/             ← tested pipeline + README (env.sh points at the shared toolkit)
├── work/                ← intermediates (safe to delete)
├── previews/finishing_comparison/
└── outputs/
```
Then open Claude Code in `my-trip/` and run `/travel-reel`. One cafe visit or a 14-day trip: the skill
detects the scope from the clips and, for several places, proposes a menu of reels (each built in
`reels/<id>/`, sharing the raw clips and proxies).

## Updating the skill

```bash
cd ~/.claude/skills/travel-reel && git pull                                   # get latest on another Mac
cd ~/.claude/skills/travel-reel && git add -A && git commit -m "..." && git push   # after improving it
```

Limits: macOS on Apple silicon (Homebrew in `/opt/homebrew`, MoltenVK; captions use macOS system fonts
Futura / Avenir Next / Didot and Apple Color Emoji). Sound effects are synthesised in code (no sample files).
Map data drawn by the route-map module is © OpenStreetMap contributors (credit it in the post caption).
