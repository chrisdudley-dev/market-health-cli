# ANDROID-UI-RESUME-001 — first UI phase gate

**PASS: fixed and validated before visual polish.**

The original failed candidate and its [natural-idle evidence](../NATURAL_IDLE_DEBUG_RESULT.md)
remain unchanged on `android/mh-policy` at `259181b`. The UI branch starts from
that preserved baseline. Its first production change is limited to presentation
reconciliation; no Python, policy, SQLite schema, fixture or financial formula
changed.

`MainActivity.onResume` asks the existing ViewModel to reread authoritative
state. The ViewModel calls the existing repository `state` operation, without
market fetch, refresh calculation, notification delivery or work scheduling.
It also rereads the active filtered History page. Query copies preserve the
filters; request versions prevent an obsolete history response from replacing
a newer filter result. Persistent history semantics and pagination API are
unchanged.

The deterministic Android regression seeds via the existing shared core,
launches the Activity, then stops it without destroying it. The actual
`RefreshWorker` commits a fixture through the production repository/persistence
path while the Activity is stopped. On resume, the same Activity and same
ViewModel display the newer timestamp and adopt authoritative rows, scores,
policy/reason/rescue/ownership DTOs and filtered history. No manual refresh,
navigation reset, process restart or extra calculation is used to pass this
test.

The **identical final test** was compiled against an isolated archive of the
original source and failed at the post-resume wait, establishing the negative
control. It then passed on the fixed source on actual 4096-byte and 16384-byte
x86_64 kernels. Each complete Android suite passed 12 tests with two deliberate
opt-in skips (14 runner-reported tests). Separate seed/reboot/verify probes
passed on both kernels with distinct boot IDs, followed by successful startup.
This restart case is separate from the same-Activity resume regression.

Host regression passed 637 tests plus 18 subtests; Android-pinned host passed
634 plus 18 subtests, one optional Qt collection skip and three existing pandas
warnings. Both full Android suites retain exact zero-tolerance CLI parity,
SQLite/rescue/history, WorkManager and notification checks. The debug APK's
actual-payload native gate passes all 266 libraries with no incompatibilities.

See the [gate manifest and raw synthetic test logs](evidence/resume-fix/result.json).
Provisioning initially encountered an old AVD lock and SDK image-discovery
limitation; separate disposable AVD configs using the already-installed images
resolved them. The failed setup logs remain local. Emulator results are not
physical validation of the fix. The physical S9+ still runs the original failed
debug artifact; it has not been replaced again.

The natural four-hour battery/Doze gate stays **OPEN**. No new idle run,
production signing, publishing or Strike work is part of this fix. Broader
authorized UI/UX refinement follows this passing checkpoint on the same
dedicated UI branch.
