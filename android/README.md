# Market Health for Android

The application target is native Android: Kotlin/Compose + Chaquopy-embedded Python.
No scoring formula or policy rule is implemented in a Kotlin UI component.

See [the migration report and architecture decision](../docs/android/ARCHITECTURE.md).
The completed Qt prototype is preserved separately in `../prototypes/desktop/`.

## Build

Requirements: JDK 17, Android SDK platform 36/build-tools 36.0.0, and Python
3.13 on the build host. Chaquopy 17.1.0 embeds CPython 3.13.16. NumPy 1.26.2,
pandas 2.1.3, OpenBLAS 0.3.33 build 2 and their dependencies are pinned by URL and
SHA-256 in `requirements-lock.json` for both ABIs. The OpenBLAS wheels come from
Chaquopy's explicit upstream index; the other Android wheels use its stable index.
Every build verifies all 12 wheel files before offline pip installation.

Open this `android/` directory in Android Studio, select the SDK, and build/run app.
For command line builds, create an ignored `local.properties` with `sdk.dir=...`.
Then use the Gradle wrapper:

```sh
./gradlew -PmhPython=/path/to/python3.13 :app:assembleDebug
./gradlew -PmhPython=/path/to/python3.13 :app:connectedDebugAndroidTest
./gradlew -PmhPython=/path/to/python3.13 :app:assembleRelease :app:bundleRelease :app:lintRelease
```

The APK is `app/build/outputs/apk/debug/app-debug.apk`. This is a debug build for
local installation. The candidate targets arm64-v8a and x86_64, Android 8.0/API 26+
with 4 KB or 16 KB pages. **Runtime validation currently covers API 35 x86_64
emulators on both page sizes**, including debug and AAB-derived release APKs;
physical ARM phones have not been tested. API 26 is the build minimum, not a claim
of runtime testing on every supported Android version. Release signing keys are
not stored in this repo. Without external signing inputs, release APK/AAB outputs
are unsigned. See [signing and verification](../docs/android/RELEASE_READINESS.md).

`assembleDebug`, `assembleRelease`, and `bundleRelease` require actual-payload
native audits, including ELF files inside Chaquopy `.imy` archives. Every PT_LOAD
must support 16 KB pages; directly mapped APK libraries must also have uncompressed,
16 KB-aligned ZIP data. `verify16kDependencies` retains the public release gate
name. AAB inspection establishes ELF compatibility; CI additionally generates an
APK using pinned bundletool, checks its signature/ZIP alignment, then installs it.

The `stageCore` Gradle task copies the authoritative repository Python sources into
the generated build directory. It does not maintain a fork or checked-in second copy.
Qt, PyInstaller, calibration jobs and CLI renderers are excluded from Android staging.

## Use

Refresh retrieves the configured universe. Menu opens Dashboard, Portfolio, Trading
List, Buy Candidates, Market Health, History, Policy, and Settings. Mark Owned enters
shares, manual account labels, optional cost basis per share, and notes. Tap a score
card for the exact comparisons, reason codes, rescue status, GlyphSpec and sizing.
All monetary/account values are local manual inputs; there are no account credentials
or order-placement APIs. Android app-private SQLite stores all financial state.

Settings supports approximate 15/30/60-minute background refresh. WorkManager handles
scheduling and recovery after process death/reboot. Android force-stop suspends work
until the user opens the app again. Android may defer work in Doze,
low battery or without network. There is no continuous desktop process, foreground
service or 5-minute periodic-work promise. Work retry IDs are idempotent so a retried
committed refresh cannot consume another rescue count.

Android 13+ asks for local notification permission when monitoring is enabled.
If permission/channel is denied, decisions and history still persist and notification
history records the blocked submission. Local notifications use stable IDs and
`onlyAlertOnce`; unchanged policy states do not enqueue duplicates.

## Verification

Host tests: `python -m pytest tests/test_android_parity.py tests/test_mh_policy.py`.
Run host parity with the Android-pinned Python dependencies as well as the current
CLI dependencies. Instrumentation executes the embedded Python against the same
frozen fixture and checks exact C/H1/H5/Blend/State/Stop/Buy/GlyphSpec/action/reason-code
parity, persistent rescue/history, scheduling boundaries, worker execution,
notifications and UI navigation. CI runs both actual page-size kernels, then
reboots each emulator to check SQLite rescue/history and the unique periodic
WorkManager request. Passing host checks alone does not count as Android parity.
See the [current verification matrix](../docs/android/RELEASE_READINESS.md) and
[original migration validation](../docs/android/VALIDATION.md).

The raw data transport is an Android HTTPS adapter for the existing Yahoo chart
source. It passes unadjusted daily OHLCV to the shared Python normalizer and core.
It introduces no trading rule and never fills missing scores. Source/network failure
marks data stale. The original CLI's yfinance transport remains available separately.
