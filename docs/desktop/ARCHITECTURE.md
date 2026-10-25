# Desktop implementation audit

Base: `origin/main` (1d14614), selected because repository default `pi-grid`
lacks GlyphSpec, structure levels, and the current tri-score implementation.

## Preserved sources of truth

- `engine.py`: yfinance OHLCV ingestion (`safe_download`), A–E scoring,
  asset dispatch, feature flags, current check totals. `scoring_engine.py` is an alias.
- `forecast_score_provider.py`, `forecast_features.py`, `forecast_checks_*`:
  absolute 1/5 trading-day forecast checks and structure sidecar.
- `structure_engine.py`, `stop_buy_levels.py`: contextual State and Stop/Buy levels.
- `glyph_spec.py`, `forecast_audit.py`: deterministic codec and check audit rows.
- `recommendations_engine.py:blended_utility_from_scores`: existing
  50% current + 25% H1 + 25% H5 blend. These numerical helpers are retained.
- Existing entry points: `market-health`, `market-health-pi`, `mh` use
  `dashboard_legacy.py`; `python -m market_health` exports scores via `mh_cli.py`.
- Configuration: environment feature flags, `config/`, optional jerboa caches.
- Tests: deterministic forecast fixtures, scoring range/regression fixtures,
  structure/Stop/Buy/GlyphSpec tests and CLI/wrapper tests.

## Conflicts recorded before implementation

The old recommendation modules rank replacements and link sells to buys.
The old dashboard renders these recommendations. The positions refresh wrappers
can call Schwab OAuth and account APIs. These paths must be retired, even though
this deliberately changes their old contracts. Their numerical scoring helpers
are independent and remain unchanged. Desktop ownership never reads positions
cache or a bullet marker.

The current engine can substitute fallback checks for missing data; the desktop
adapter validates actual input bars before evaluating policy. Missing required
scores remain DATA ERROR. It does not manufacture a decision from fallback data.

The prompt overlaps HOLD and WATCH when H5=C; HOLD takes precedence. SELL edges
take precedence over HOLD (including Blend). For other neutral combinations not
covered by an explicit HOLD/WATCH rule, UNKNOWN is shown. Unowned nonqualifiers
also show UNKNOWN / not BUY. This avoids inventing maintenance or entry rules.
Rescue is consecutive per owned symbol; data errors preserve its count, successful
normal refreshes reset it, and ownership edits never consume a refresh.

## Plan

1. Dedicated pure `policy/` constants, models, comparisons, explanations, tests.
2. `engine_api.py` calls existing scoring/forecast/GlyphSpec functions on one
   downloaded snapshot, retaining all computations and configured symbols.
3. SQLite `desktop/store.py` owns holdings, settings, scans, decisions, transitions,
   persistent rescue state, and a notification outbox in one transaction.
4. `desktop/service.py` is the single refresh pipeline for Qt and a policy CLI.
5. `desktop/app.py`: eight native Qt screens, worker refresh, tray/timer,
   local notification delivery, audit drilldown and manual sizing.
6. Packaging, deterministic UI smoke tests, CLI checks, scoring fixture audit.

## Baseline

Python 3.14.4 in an isolated venv. Initial pytest run: ten failures caused largely
by the venv's bin directory missing from PATH in subprocess wrappers; rerun with
PATH set leaves one pre-existing failure in the legacy recommendation-export shim
test. The final retained/new suite passes 603 tests plus 18 subtests. Editable
installation initially also fails on the
overescaped setuptools-scm tag regex. No scoring files were edited for baseline.
