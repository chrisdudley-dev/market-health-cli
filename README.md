# Market Health CLI

Terminal-first sector health dashboard and score exporter.

Educational tool only - not investment advice.

## Install

From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

`.[dev]` installs the runtime dependencies plus the local test and lint tools. If you only want the runtime app, use `python -m pip install -e .` instead.

## Quickstart

Run the live UI in compact Pi mode:

```bash
market-health --pi-grid --grid-cols 0
```

The same UI can also be launched with:

```bash
market-health-pi --pi-grid --grid-cols 0
python market_ui.py --pi-grid --grid-cols 0
python -m market_health.market_ui --pi-grid --grid-cols 0
```

If you want generated sample data instead of live scoring, add `--demo`.

## Supported Commands

Packaging exposes these console scripts:

- `market-health`
- `market-health-pi`

Both scripts point to the terminal UI entry point in `market_ui.py`.

Supported direct Python entry points:

- `python market_ui.py`
- `python -m market_health.market_ui`
- `python -m market_health`
- `python -m market_health.mh_cli`

`python -m market_health` delegates to `market_health.mh_cli` through `market_health/__main__.py`.

## Live UI vs Offline JSON

The UI has two distinct data paths:

- Live mode: when neither `--demo` nor `--json` is used, the UI calls `compute_scores(...)` in the engine and renders those live scores directly.
- Demo mode: `--demo` replaces live data with generated sample rows.
- Offline mode: `--json` bypasses live scoring and renders prebuilt JSON artifacts.

That separation matters:

- The score export written by `market-health`, `python -m market_health`, or `python -m market_health.mh_cli` is an exported artifact, not a live input source for the UI.
- `--json` is for offline rendering from already-produced JSON.

The JSON renderer accepts:

- score JSON with sector rows and `categories/checks`
- environment JSON such as `~/.cache/jerboa/environment.v1.json`, which contains a top-level `sectors` array
- UI contract JSON such as `~/.cache/jerboa/market_health.ui.v1.json`, which carries `data.sectors`

Examples:

```bash
# Write score JSON from the engine
python -m market_health.mh_cli --out scores.json

# Render that JSON offline
market-health --json scores.json --pi-grid --grid-cols 0

# Render the UI contract export offline
market-health --json ~/.cache/jerboa/market_health.ui.v1.json --pi-grid --grid-cols 0
```

## Raspberry Pi And Wrapper Scripts

The repo includes Pi-friendly cache and wrapper scripts under `scripts/jerboa/`.

Install the repo-managed wrappers and user units:

```bash
bash scripts/jerboa/install_market_health.sh
```

That installs symlinks in `~/bin` for:

- `jerboa-market-health-refresh`
- `jerboa-market-health-positions-refresh`
- `jerboa-market-health-refresh-all`
- `jerboa-market-health-ui-export`
- `jerboa-market-health-status`
- `jerboa-market-health-alert`

Typical Pi workflow:

```bash
# Refresh the cache bundle
jerboa-market-health-refresh-all --force

# Write the UI contract cache artifact
jerboa-market-health-ui-export

# Render the cached UI contract offline in the terminal
market-health --json ~/.cache/jerboa/market_health.ui.v1.json --pi-grid --grid-cols 0
```

For slower hardware, `--grid-cols 0` auto-fits the compact grid to the terminal width. `--mono` switches to monochrome output.

## Project Layout

```text
market_health/
  engine.py           score computation and data shaping
  market_ui.py        Rich-based terminal UI and JSON renderer
  mh_cli.py           score export CLI
  __main__.py         package entry point -> mh_cli
market_ui.py          top-level launcher for the UI
scripts/
  jerboa/             repo-managed wrappers, install script, systemd units
  cache/              local cache refresh helpers
docs/
  SCORING.md          scoring model and dimensions
  UI_CONTRACT.md      UI contract shape and stability notes
  TESTING.md          fixture and regeneration workflow
```

## Architecture

The current app has a clear split between computation and presentation:

- `market_health.engine.compute_scores(...)` produces the live sector scores.
- `market_health.market_ui` renders those scores in Rich tables or the Pi grid.
- `market_health.mh_cli` exports score JSON and optional CSV from the engine.
- `market_ui.py` is a compatibility launcher for the UI, while `market_health/__main__.py` launches the score-export CLI.

When the UI runs in live mode, it computes scores directly from the engine. When it runs with `--json`, it becomes an offline renderer for score JSON, environment JSON, or the UI contract artifact.

## Documentation

- [Scoring model](docs/SCORING.md)
- [UI contract](docs/UI_CONTRACT.md)
- [Testing and fixtures](docs/TESTING.md)
- [UI contract example](docs/examples/market_health.ui.v1.example.json)
- [Pi wrapper installer](scripts/jerboa/install_market_health.sh)
- [UI contract exporter](scripts/jerboa/bin/jerboa-market-health-ui-export)
- [Cache refresh helper](scripts/cache/refresh_market_health_cache.sh)
