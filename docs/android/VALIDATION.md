# Original Android migration validation record

This is historical evidence for the initial Python 3.11 / 4 KB debug artifact.
Its outstanding 16 KB/reboot gates were subsequently resolved in the
[current release verification matrix](RELEASE_READINESS.md). The live 25-symbol
refresh below belongs to this original stack; it has not been rerun on the new
Python 3.13 stack. Statements below describe the original artifact only.

Validated 2026-10-25 against repository main commit
`1d14614ddc13c62fd273eb82b3cddc36e6d3b298`.

## Executed checks

| Check | Observed result |
|---|---|
| Full CLI/core/policy/storage suite | 612 passed, 18 subtests passed |
| Host with Android-pinned CPython 3.11, NumPy 1.26.2, pandas 2.1.3 | 93 passed |
| Ruff static checks and formatting | Passed; 277 Python files checked for formatting |
| Gradle app + test APK builds | Successful for arm64-v8a and x86_64 |
| Android lint | 0 errors, 10 warnings (including dependency-version notices) |
| Android 15/API 35 x86_64, 4 KB software emulator | 8 instrumentation tests passed in 98.831 seconds |
| Live refresh on the Android emulator | 25 universe symbols calculated; status OK; no DATA ERROR rows |
| Native dependency ELF audit | Original pip-only audit covered 132 libraries at 4 KB; the later full-APK audit found 272 ELF libraries, 40 incompatible with 16 KB |

The emulator executes the actual packaged Python implementation. The exact fixture
compares C, H1, H5, Blend, State, Stop, Buy, GlyphSpec, policy action and reason codes
against the frozen CLI reference. No numerical tolerance was relaxed. Separate host
checks execute the existing CLI mathematics directly and an actual CLI subprocess
against the same explicit OHLCV fixture.

The eight device tests cover:

1. Exact CLI versus embedded Android calculation/policy parity.
2. Persistent rescue/history across fresh database instances, a second rescue
   becoming SELL, and no repeated SELL notification.
3. A committed refresh retry retaining its cycle identity; a new cycle uses a new ID.
4. WorkManager minimum interval enforcement.
5. Native UI manual holding creation and removal.
6. Opening all eight application destinations.
7. Android notification permission denial recorded persistently, permission-granted
   submission visible through NotificationManager, and unchanged HOLD suppression.
8. Raw chart responses with fully empty market-session rows producing exactly the
   same fixture results as the CLI. Partially missing rows still fail host validation.

Source comparison verified that calculation definitions in the existing current,
forecast, structure, Stop/Buy and GlyphSpec modules remain unchanged. The only engine
function alteration is a transport availability guard for injected OHLCV. The shared
Blend numerical helper remains the existing implementation. The chart normalizer
removes wholly empty provider rows, matching the existing CLI downloader; it does
not fill partial data or manufacture market sessions. Kotlin contains no
scoring formulas or policy evaluator.

## Limits and remaining migration work

This is a **4 KB debug APK**, not a general signed release. Stable embedded
NumPy/pandas/OpenBLAS/Fortran libraries include 4 KB ELF load alignment. The app checks
device page size before starting Python and shows a compatibility message on 16 KB
devices. General release tasks fail the native alignment gate until compatible
wheels are rebuilt. Those wheels then need exact parity on both page sizes and ABIs.
The issue is documented [upstream](https://github.com/chaquo/chaquopy/issues/1464).

The arm64-v8a APK libraries were built, but a physical ARM phone and a 16 KB device
were not available for runtime verification. Reboot/Doze behavior relies on Android
WorkManager; elapsed background timing and physical-device battery behavior require
longer device testing. Store persistence, notification state, and retry identities
were exercised directly; a phone reboot was not simulated in this test run.

Release signing, distribution, and a 16 KB dependency rebuild remain outstanding.
No brokerage, bank, credentials, or automated order integration is included. Market
data comes from a public chart source and source failure is surfaced as stale/error.
Fixture data and QA ownership are contained in the test APK, not the application APK.

The original CLI remains installed and testable. Qt/PySide6, desktop tray APIs, and
PyInstaller files are isolated in `prototypes/desktop/` and excluded from Android.
