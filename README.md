# Market Health

**Android is the application target.** The existing Python CLI/calculation engine
remains available and testable. The Android UI embeds that same Python engine with
Chaquopy; Kotlin contains no scoring or MH Policy implementation.

[Android build and usage](android/README.md) ·
[Architecture and migration](docs/android/ARCHITECTURE.md) ·
[Release verification matrix](docs/android/RELEASE_READINESS.md)

## Application

Native Android screens cover Dashboard, the Market Health universe, manual Portfolio,
Trading List, Buy Candidates, History, Policy and Settings. SQLite owns holdings,
account labels, shares, Net Liq, settings, prior policy states, rescue counts, scans,
transitions and the notification outbox. WorkManager supports approximate 15/30/60
minute background refresh. Notifications report meaningful owned-position transitions.

The current candidate passed exact parity on 4 KB and 16 KB Android x86_64 emulators,
using both the debug APK and an APK generated from the release AAB. Actual packaged
native libraries pass the enforced 16 KB ELF/ZIP gate for arm64-v8a and x86_64.
Both APK variants also passed exact parity and the required instrumentation on
a physical Galaxy S9+ (Android 10/API 29, arm64-v8a, 4 KB), with additional live
refresh and reboot-persistence checks. Extended phone battery/Doze acceptance
and production signing remain outstanding; this is not a general release.
See the [physical validation report](docs/android/PHYSICAL_S9_VALIDATION.md)
and release verification matrix for evidence and scope.

No brokerage/bank integration and no automatic trading are included. BUY and SELL
are independent. Cash never relaxes the policy. Missing inputs show DATA ERROR;
neutral combinations not explicitly covered by the supplied policy show UNKNOWN.

## Shared architecture

- `engine.py`, `forecast_*`, `structure_engine.py`, `stop_buy_levels.py`: existing math.
- `glyph_spec.py`, `forecast_audit.py`: existing GlyphSpec and audit generation.
- `engine_api.py`: explicit-OHLCV calculation boundary and optional CLI data transport.
- `policy/`: deterministic MH Policy, constants, reason codes and explanations.
- `storage/sqlite.py`: authoritative local ownership, history and persistent state.
- `application/`: portable refresh/sizing/logging services.
- `android_bridge.py`: JSON application boundary for Android.
- `android/`: native UI, HTTPS transport, WorkManager and notification adapters.

The previous PySide6/Qt GUI, system tray/timers and PyInstaller packaging are retained
under `prototypes/desktop/` as an isolated optional prototype. They are not the product
or Android deployment target, and no core layer imports them.

## Python CLI

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
market-health --refresh --pi-grid
market-health --out policy-decisions.json
market-health --demo --pi-grid
python -m market_health --out current-checks.json
```

Installed terminal entry points remain `market-health`, `market-health-pi` and `mh`.
The CLI and Android use the same current/forecast/Blend/structure/GlyphSpec functions
and policy. [Frozen parity fixtures](tests/fixtures/android/) check the same input
through the CLI/core and embedded Android boundary.

## Verification and reference

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Android runtime parity additionally requires instrumentation on an emulator/device;
see `android/README.md`. Optional Qt prototype tests skip without PySide6.

- [Scoring semantics](docs/SCORING.md)
- [Original regression fixture workflow](docs/TESTING.md)
- [Retired brokerage/replacement contracts](docs/desktop/RETIRED.md)

MIT License · Christopher Dudley
