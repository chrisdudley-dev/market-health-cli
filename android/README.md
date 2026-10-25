# Market Health for Android

The application target is native Android: Kotlin/Compose + Chaquopy-embedded Python.
No scoring formula or policy rule is implemented in a Kotlin UI component.

See [the migration report and architecture decision](../docs/android/ARCHITECTURE.md).
The completed Qt prototype is preserved separately in `../prototypes/desktop/`.

## Build

Requirements: JDK 17 or 21, Android SDK platform 36/build-tools 36.0.0, and Python
3.11 on the build host. NumPy 1.26.2 and pandas 2.1.3 are pinned in the Android
build because compatible prebuilt Android wheels are available for both ABIs.

Open this `android/` directory in Android Studio, select the SDK, and build/run app.
For command line builds, create an ignored `local.properties` with `sdk.dir=...`.
Then use the Gradle wrapper:

```sh
./gradlew -PmhPython=/path/to/python3.11 :app:assembleDebug
./gradlew -PmhPython=/path/to/python3.11 :app:connectedDebugAndroidTest
```

The APK is `app/build/outputs/apk/debug/app-debug.apk`. This is a debug build for
local installation, not a signed store release. Supported ABIs: arm64-v8a and
x86_64; Android 8.0/API 26 or later on **4 KB memory-page devices**. Native dependency
rebuilding and 16 KB device parity are a general-release gate. The app checks this
compatibility before starting its calculation engine. Release signing keys are not stored in this repo.

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
parity, persistent rescue/history, and valid scheduling boundaries. Passing host
checks alone does not count as device parity. See [recorded validation](../docs/android/VALIDATION.md).

The raw data transport is an Android HTTPS adapter for the existing Yahoo chart
source. It passes unadjusted daily OHLCV to the shared Python normalizer and core.
It introduces no trading rule and never fills missing scores. Source/network failure
marks data stale. The original CLI's yfinance transport remains available separately.
