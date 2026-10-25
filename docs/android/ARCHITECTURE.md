# Android target and migration decision

Android is the final product target. The completed desktop work is an optional,
isolated prototype under `prototypes/desktop/`, not a deployment path.

## State when the target changed

The previous implementation had added the engine adapter, deterministic MH Policy,
explanations, manual portfolio/accounts, SQLite persistence, rescue/history/transition
logic, sizing, logging, CLI integration and regression tests. **Yes, PySide6/Qt UI
implementation had already begun**, including screens, a Qt background worker/timer,
tray behavior and desktop notifications. PyInstaller packaging/build configuration
and desktop icons also existed. These platform pieces are preserved only as an
isolated prototype. No new desktop UI work was added after the Android correction.

The existing C/H1/H5/Blend/State/Stop/Buy/GlyphSpec calculation definitions remain
reusable unchanged. The new policy, storage and application logic are portable and
were relocated into neutral packages; Android supplies lifecycle, data transport,
private storage paths and notification delivery. Qt widgets/workers, tray APIs and
PyInstaller packaging are not reusable Android platform components.

## Completed work retained

The existing current, forecast, structure, Stop/Buy and GlyphSpec engines remain
in Python. Added portable work includes the exact MH Policy, rule explanations,
manual holdings/accounts, SQLite schema and audit trail, persistent rescue state,
notification transition/outbox logic, sizing, shared engine adapter and CLI.
The initial migration host run passed 612 tests plus 18 subtests. The initial Android-pinned host run
passed 93 tests; the Android 15 emulator passed eight instrumentation tests,
including exact embedded-runtime parity and real OS notification delivery.
See the [original validation](VALIDATION.md) for that historical run and the
[current release matrix](RELEASE_READINESS.md) for the subsequent 16 KB work.

The portable store has moved from `desktop/store.py` to `storage/sqlite.py`.
Application orchestration, sizing and structured logging moved to `application/`.
Qt screens, Qt worker/timer, tray APIs, OS popup delivery and PyInstaller packaging
are isolated under `prototypes/desktop/`. No core module imports them. The primary
Python package and Android source staging exclude that prototype.

## Technology evaluation

| Approach | Assessment |
|---|---|
| Kotlin/Compose + embedded Python (Chaquopy) | Selected. Native Android lifecycle, WorkManager and notifications; same Python mathematics and policy. |
| Flutter/React Native + Python bridge | Possible, but still requires the same Python embedding and adds another bridge without a correctness advantage. |
| Kivy/python-for-android or BeeWare | Could retain Python, but package recipes and Android background/notification integration introduce more build work for this repository. |
| Kotlin port of mathematics | Rejected: duplicates the authoritative implementation and creates unnecessary parity risk. |
| Remote Python service | Rejected for this local application: adds server availability and a second deployment responsibility. |

Chaquopy 17.1 supports CPython embedding and Android API 24+. This app uses API 26+
for native Android time/notification APIs. Its published package index contains
NumPy 1.26.2 and pandas 2.1.3 wheels for Python 3.13 on arm64-v8a and x86_64.
The release candidate uses CPython 3.13.16 and OpenBLAS 0.3.33 build 2; all wheel
bytes are hash-locked. NumPy/pandas version numbers remain unchanged from the
initial Python 3.11 build. See [native provenance](NATIVE_DEPENDENCIES.md) for the
ABI-specific build changes and the full regression/runtime evidence. Existing CLI
dependency versions remain supported and testable separately.

Current yfinance uses curl_cffi, for which the checked Chaquopy package index has
no Android wheel. This affects transport, not scoring. `engine.py` now permits its
transport import to be absent when OHLCV is injected. No scoring expression changes.
Android fetches raw daily chart data with Android HTTPS and passes it to the shared
Python input normalizer. No price repair, score transformation, or policy is in UI.
Provider failure yields stale/error status and never a fabricated decision.

## Layers

1. `engine.py`, `forecast_*`, `structure_engine.py`, `stop_buy_levels.py`,
   `glyph_spec.py`: authoritative calculations.
2. `engine_api.calculate_frames`: explicit immutable OHLCV boundary shared by CLI
   and Android. Optional calendar inputs are part of the fixture contract.
3. `policy/`: authoritative actions, reason codes and explanations.
4. `storage/sqlite.py`: one SQLite ownership/history/rescue schema.
5. `application/`, `android_bridge.py`: application operations and JSON boundary.
6. Android repository + WorkManager + notifications: lifecycle and platform adapters.
7. Kotlin/Compose: renders returned values and submits user edits; no financial math.

Room would be reasonable for a Kotlin-owned schema. It is deliberately not added as
a second writer: reusing the existing SQLite implementation keeps portfolio, rescue,
transactions and transition logic authoritative in one place. Android supplies an
explicit private `context.filesDir` database path. No desktop home directory is used.

## Background work and notifications

A unique WorkManager periodic request supports 15/30/60-minute intervals with network
constraints and exponential retry. Timing is approximate and subject to Doze/battery
restrictions. Android does not offer 5/10-minute periodic WorkManager execution.
No foreground service or exact alarm is required for this product cadence.
WorkManager persists scheduling across process death/reboot; SQLite persists state.

Both manual and scheduled refresh call the same repository/core operation, then
publish owned action transitions from the persisted outbox. Notification IDs are
stable and `onlyAlertOnce` suppresses repeated alerts during a crash/retry window.
Android 13+ POST_NOTIFICATIONS permission is requested in context. Denial is recorded
without discarding portfolio history or changing a policy action.

## Parity gates

Frozen OHLCV + calendar + ownership/rescue fixtures are passed to the CLI/core adapter
and to the Android-embedded module. Compare C, H1, H5, Blend, State, Stop, Buy, GlyphSpec,
policy action and reason codes. A host test alone does not prove Android runtime parity:
an instrumentation test on an emulator/device must execute the packaged Python module.
Exact golden comparisons are gates; a mismatch must be investigated, not accepted by
loosening tolerances or changing formulas. Platform runtimes not executed are reported.

## Migration sequence

1. Isolate desktop UI/deployment; keep CLI/core tests green.
2. Separate data acquisition from calculations; freeze parity fixtures.
3. Pin Android-compatible Python dependencies and stage the exact source files.
4. Embed the Python core behind a JSON API; run host and Android parity tests.
5. Add native portfolio, score/audit, candidate/history/settings screens.
6. Add unique WorkManager scheduling, permission-aware local notifications and
   persisted transition delivery; test restart and duplicate suppression.
7. Build/install a debug APK; retain device/runtime verification evidence. Release
   signing and Play distribution are separate from local debug installation.

Sources: [Chaquopy setup](https://chaquo.com/chaquopy/doc/current/android.html),
[package index](https://chaquo.com/pypi-13.1/),
[WorkManager periodic work](https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work#schedule_periodic_work),
[notification permission](https://developer.android.com/develop/ui/compose/notifications/notification-permission).

## Verified native dependency release gate

The original Python 3.11 APK had 40 incompatible native libraries, each traced to
its exact source wheel. CPython 3.13 wheels of the same NumPy/pandas versions and
explicitly pinned OpenBLAS 0.3.33 builds resolve their alignment failures without
changing financial formulas. All 266 ELF libraries in the candidate APK/AAB pass.

`verify16kDependencies` now inspects the actual release APK; release assembly and
bundle tasks enforce the same gate. CI proves rejection by injecting a 4 KB ELF
into a final APK, then rebuilding a clean candidate. Both 4 KB and 16 KB emulators
execute exact parity on debug and AAB-derived release APKs. These results establish
x86_64 runtime validation and arm64 build compatibility. Physical ARM execution,
vendor battery behavior and production signing remain manual release gates.
