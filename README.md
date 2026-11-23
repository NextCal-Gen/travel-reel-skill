# travel-reel: Claude Code skill

Raw travel clips (Insta360 360°, iPhone, Samsung, DJI) in → cinematic 9:16 Instagram Reel out.
This repo **is** the skill folder: clone it to `~/.claude/skills/travel-reel` and run `/travel-reel`
in Claude Code from a trip folder.

| File | What |
|---|---|
| `SKILL.md` | The workflow Claude follows (phases, gates, defaults, verified pitfalls) |
| `bootstrap.sh` | Checks/creates the shared toolkit; sets up new trip folders |
| `CLAUDE.template.md` | Per-trip `CLAUDE.md` (standing defaults, kickoff questions, hard rules) |
| `template/scripts/` | The tested pipeline (see `template/README.md` for run order + what to edit per trip) |
| `template/looks/` | Standing look (Look 2 "warm cinematic") + Insta360/Samsung camera-match LUTs |
| `requirements-*.lock` | Exact Python package versions for the shared toolkit |

## Setup on a new Mac (Apple silicon)

1. Install Claude Code and sign in; install [Homebrew](https://brew.sh).
2. Clone this repo into the skills folder:
   ```bash
   gh repo clone NextCal-Gen/travel-reel-skill ~/.claude/skills/travel-reel
   ```
3. System tools (about 30–40 min; the FFmpeg build with zimg/libplacebo/libvmaf is the long part):
   ```bash
   brew install media-info exiftool python@3.12 molten-vk
   brew tap homebrew-ffmpeg/ffmpeg && brew trust --formula homebrew-ffmpeg/ffmpeg/ffmpeg
   brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg --with-libplacebo --with-libvmaf
   ```
4. Shared toolkit (`~/travel-reel-toolkit`, about 2 GB: Python venv, RIFE, models), then verify:
   ```bash
   ~/.claude/skills/travel-reel/bootstrap.sh --create
   ~/.claude/skills/travel-reel/bootstrap.sh --check
   ```
   Shortcut: run `/travel-reel` in an empty trip folder; Phase 0 checks everything and asks before installing.

## New trip

```bash
~/.claude/skills/travel-reel/bootstrap.sh --init-project ~/Desktop/my-trip
```
Creates:
```
my-trip/
├── CLAUDE.md            ← set the trip name; standing defaults + kickoff questions inside
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
Then open Claude Code in `my-trip/` and run `/travel-reel`.

## Updating the skill

```bash
cd ~/.claude/skills/travel-reel && git pull                                   # get latest on another Mac
cd ~/.claude/skills/travel-reel && git add -A && git commit -m "..." && git push   # after improving it
```

Limits: macOS on Apple silicon (Homebrew in `/opt/homebrew`, MoltenVK, Avenir Next font).
Map data drawn by the route-map module is © OpenStreetMap contributors (credit it in the post caption).
