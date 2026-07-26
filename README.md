# Market Health CLI

Terminal-first market-health scoring and dashboard tooling for sector ETFs and related portfolio workflows.
The project is built around a compact Rich-based UI, JSON cache artifacts, and small refresh/export scripts that can run locally or on a Raspberry Pi.

> Educational tool only. Not investment advice.

## What this repo provides

- A terminal dashboard for current sector health
- A scorer that exports JSON/CSV score artifacts
- Cache refresh wrappers for Pi/Jerboa-style automation
- Contract docs and fixtures for UI, scoring, positions, recommendations, events, and forecast scores

## Install

Create a virtual environment and install the project in editable mode:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

If you are on a Raspberry Pi, `pip` can be much faster with `piwheels`:

```bash
export PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip wheel
python -m pip install -e ".[dev]"
```

## Quickstart

1. Activate the environment.
2. Run the UI in Pi Grid mode.
3. Use `--demo` if you want generated sample data instead of live data.

```bash
market-health --pi-grid --grid-cols 0
market-health --pi-grid --grid-cols 0 --demo
```

If you prefer the repository root launcher, the same UI is available through:

```bash
python market_ui.py --pi-grid --grid-cols 0
```

## Supported console scripts

The package exposes two console entry points from `pyproject.toml`:

- `market-health`
- `market-health-pi`

Both currently dispatch to the same terminal UI entry point. `market-health-pi` is the wrapper-friendly name for Pi/Jerboa usage.

Examples:

```bash
market-health --pi-grid --grid-cols 0
market-health-pi --pi-grid --grid-cols 0
```

## Entry points

The main runtime surfaces are:

- `python -m market_health` -> score export CLI via `market_health.__main__`
- `python -m market_health.mh_cli` -> score export CLI
- `python market_health/mh_cli.py` -> score export script form
- `python -m market_health.market_ui` -> UI module entry point
- `python market_ui.py` -> repository-root UI launcher

The UI accepts the current flags implemented in `market_health/market_ui.py`:

- `--sectors`
- `--topk`
- `--mono`
- `--watch`
- `--json`
- `--demo`
- `--period`
- `--interval`
- `--ttl`
- `--pi-grid`
- `--grid-cols`

Useful UI examples:

```bash
# Live data in compact grid mode
market-health --pi-grid --grid-cols 0

# Render from a saved JSON file
market-health --json ~/.cache/jerboa/market_health.ui.v1.json --pi-grid --grid-cols 0

# UI module form
python -m market_health.market_ui --pi-grid --grid-cols 0

# Standard non-grid terminal view
market-health --sectors XLK XLF XLY XLV
```

## JSON workflows

The repo uses JSON cache artifacts as the stable handoff between refreshers, exporters, and the UI.

### UI contract

The main UI artifact is:

- `~/.cache/jerboa/market_health.ui.v1.json`

It is documented in [`docs/UI_CONTRACT.md`](docs/UI_CONTRACT.md) and used by the Pi/Jerboa wrappers as the human-readable dashboard payload.

### Score export

The scorer CLI writes sector score JSON, and can also write CSV totals:

```bash
python -m market_health.mh_cli --out scores.json
python -m market_health.mh_cli --out scores.json --out-csv scores.csv
```

The score export is the source input for the UI’s live mode and for downstream validation workflows.

### Cache artifacts

Common local cache files:

- `~/.cache/jerboa/environment.v1.json`
- `~/.cache/jerboa/market_health.sectors.json`
- `~/.cache/jerboa/positions.v1.json`
- `~/.cache/jerboa/recommendations.v1.json`
- `~/.cache/jerboa/forecast_scores.v1.json`
- `~/.cache/jerboa/calibration.v1.json`
- `~/.cache/jerboa/calendar.v1.json`
- `~/.cache/jerboa/state/market_health_refresh_all.state.json`

These files are read by the UI exporter and the refresh wrappers. They are not committed to the repository.

## Raspberry Pi and Jerboa wrappers

The `scripts/jerboa/bin/` directory contains the wrapper commands used for Pi/Jerboa-style installs:

- `jerboa-market-health-refresh`
- `jerboa-market-health-refresh-all`
- `jerboa-market-health-status`
- `jerboa-market-health-ui-export`
- `jerboa-market-health-positions-refresh`
- `jerboa-market-health-recommendations-refresh`
- `jerboa-market-health-forecast-scores-refresh`
- `jerboa-market-health-calendar-refresh`
- `jerboa-market-health-calibration-refresh`
- `jerboa-market-health-alert`

Typical flow:

1. Refresh positions and market caches.
2. Export the combined UI JSON contract.
3. Render the Pi grid from the exported contract.

Examples:

```bash
scripts/cache/refresh_market_health_cache.sh
scripts/jerboa/bin/jerboa-market-health-ui-export
market-health --json ~/.cache/jerboa/market_health.ui.v1.json --pi-grid --grid-cols 0
```

For a compact welcome view on small displays, `scripts/cache/market_health_show_grid.sh` launches the Pi grid directly.

## Project layout

```text
market_health/              core scoring, UI, and provider modules
market_ui.py                repository-root UI launcher
mh_make_scores.py           helper entry for score generation
scripts/                    export, validation, and refresh utilities
scripts/cache/              cache refresh helpers
scripts/jerboa/bin/         Pi/Jerboa wrapper commands
docs/                      scoring, UI, positions, recommendations, events, testing, contracts
tests/                     fixture-backed regression checks
```

## Architecture overview

- `market_health.engine` computes sector scores from market data
- `market_health.mh_cli` exports score JSON and CSV artifacts
- `market_health.market_ui` renders the terminal dashboard and Pi Grid
- `scripts/export_*.py` and `scripts/validate_*.py` handle contract-specific JSON workflows
- `scripts/jerboa/bin/*` compose local caches into refreshable Pi/Jerboa runtime commands

The UI supports both live computation and offline rendering from JSON files. In Pi Grid mode it prefers a compact display and can read the exported UI contract directly.

## Documentation

Current docs under `docs/`:

- [`docs/SCORING.md`](docs/SCORING.md)
- [`docs/UI_CONTRACT.md`](docs/UI_CONTRACT.md)
- [`docs/TESTING.md`](docs/TESTING.md)
- [`docs/positions.v1.md`](docs/positions.v1.md)
- [`docs/recommendations.v1.md`](docs/recommendations.v1.md)
- [`docs/events_provider.md`](docs/events_provider.md)
- [`docs/contracts/forecast_scores.v1.md`](docs/contracts/forecast_scores.v1.md)
- [`docs/scoring_real_vs_placeholder.md`](docs/scoring_real_vs_placeholder.md)

Fixtures and examples live under `tests/fixtures/` and `docs/examples/`.

## Verification and maintenance

For routine local checks, use the project’s documented test workflow:

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
```

If you intentionally change JSON contracts or score outputs, update the corresponding fixtures and docs together. `docs/TESTING.md` has the regeneration commands for the UI contract signature and the scoring regression snapshots.

## Troubleshooting

- No colors in the terminal: try a different terminal or use `--mono`.
- Pi installs are slow: set `PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple`.
- Want offline rendering: point the UI at a saved JSON file with `--json`.
- Need fresh cache state: run the refresh wrapper or `scripts/cache/refresh_market_health_cache.sh`.
- Want status/debug output for the current cache chain: use `jerboa-market-health-status` or inspect `~/.cache/jerboa/state/market_health_refresh_all.state.json`.

## License

MIT © Christopher Dudley
