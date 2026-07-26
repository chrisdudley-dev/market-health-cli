# Market Health CLI

A terminal-first, color-coded dashboard that summarizes sector market health at a glance. Built with [Rich](https://github.com/Textualize/rich) and designed to work well on small screens, including Raspberry Pi displays.

> Educational tool only - not investment advice.

## Highlights

- Pi Grid mode for compact, single-grid terminal layouts.
- Live, demo, or offline JSON rendering.
- Separate score-export CLI paths and UI launcher paths.
- Raspberry Pi wrapper scripts plus systemd units for refresh and local serving.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

On Raspberry Pi, you can optionally point pip at piwheels before installing:

```bash
export PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple
python -m pip install -e ".[dev]"
```

## Run the UI

The installed console commands are UI launchers:

- `market-health`
- `market-health-pi`

Both are mapped to `market_ui:main` in `pyproject.toml`, so they launch the Rich UI and do not write score exports.

```bash
market-health --pi-grid --grid-cols 0
market-health-pi --pi-grid --grid-cols 0

# Direct module/script launch also works
python market_ui.py --pi-grid --grid-cols 0
```

## UI Modes

- Live UI: default mode when neither `--demo` nor `--json` is set. This fetches live scores through the engine.
- Demo UI: `--demo` generates repeatable sample data and ignores live or JSON input.
- Offline JSON: `--json PATH` renders sector data from a file without fetching live data.

The offline path can render score exports, the UI contract at `~/.cache/jerboa/market_health.ui.v1.json`, or another JSON file that contains sector entries in the shape the UI expects. When the input is a UI contract, the UI can also show the embedded recommendation summary.

Useful flags:

- `--pi-grid`: compact single-grid view for small displays.
- `--grid-cols N`: number of grid columns; use `0` to auto-fit.
- `--watch N`: auto-refresh every `N` seconds.
- `--mono`: monochrome output.

Examples:

```bash
# Live Pi Grid
market-health --pi-grid --grid-cols 0

# Deterministic demo layout
market-health --demo --pi-grid --grid-cols 4

# Offline render from a previously exported file
market-health --json scores.json --pi-grid --grid-cols 0
```

## Export Score JSON

Score export is separate from the UI launchers. Use one of these equivalent entry points:

```bash
python -m market_health --out scores.json
python -m market_health.mh_cli --out scores.json
python market_health/mh_cli.py --out scores.json
```

Each command writes score JSON to the path given by `--out` and can also emit CSV with `--out-csv` if needed.

## Raspberry Pi Wrappers

Repository scripts under `scripts/jerboa/bin/` wire the cache refresh flow together:

- `scripts/jerboa/bin/jerboa-market-health-ui-export` writes `~/.cache/jerboa/market_health.ui.v1.json`.
- `scripts/jerboa/bin/jerboa-market-health-refresh-all` refreshes market data, positions, recommendations, forecast scores, and then runs the UI export.
- `scripts/jerboa/bin/jerboa-market-health-refresh` refreshes the market cache.
- `scripts/jerboa/bin/jerboa-market-health-status` reports the current refresh state.

The matching systemd user units under `scripts/jerboa/systemd/user/` are:

- `jerboa-market-health-refresh-all.service` to run the refresh pipeline.
- `jerboa-market-health-refresh-all.timer` to run it every 30 minutes after boot.
- `jerboa-market-health-ui.service` to serve `~/.cache/jerboa` on `127.0.0.1:8765`.
- `jerboa-market-health-refresh-all-failure.service` to trigger the alert wrapper on failure.

## Architecture

- `market_health/engine.py` computes the sector checks and totals.
- `market_health/mh_cli.py` is the score-export CLI.
- `market_health/__main__.py` delegates `python -m market_health` to the exporter.
- `market_health/market_ui.py` renders the Rich dashboard, including Pi Grid mode and offline `--json` rendering.
- `market_ui.py` is the top-level UI launcher used by the installed console scripts.
- Cache artifacts live under `~/.cache/jerboa/`, and the UI reads from those exported files when available.

## Project Layout

```text
market_health/                  scoring engine, exporter CLI, and UI renderer
market_health/engine.py         score computation
market_health/mh_cli.py         score export CLI
market_health/__main__.py       package entrypoint for score export
market_health/market_ui.py      Rich terminal UI and Pi Grid
market_ui.py                    top-level UI launcher
scripts/jerboa/bin/             Raspberry Pi wrapper scripts
scripts/jerboa/systemd/user/    user-level systemd units
docs/                           scoring, UI contract, and testing docs
```

## Docs

- `docs/SCORING.md` - scoring semantics and feature flags.
- `docs/UI_CONTRACT.md` - UI contract fields and shape.
- `docs/TESTING.md` - local checks and fixture regeneration.

## Troubleshooting

- No colors in terminal: try a different terminal or add `--mono`.
- Slow installs on Pi: set `PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple`.
- Offline rendering: use `--json` with a previously exported JSON file.

## License

MIT Copyright Christopher Dudley
