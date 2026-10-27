# Galaxy S9+ physical ARM validation

Validation date: 2026-10-26 (America/New_York).

The user supplied an authorized USB-connected Samsung Galaxy S9+ (SM-G965U).
ADB identified Android 10/API 29, `arm64-v8a`, an emulator property of `0`, and
an actual kernel page size of 4096 bytes. This is physical ARM runtime evidence
for this device and Android version. It does not establish physical 16 KB
execution or acceptance on every Android device.

The unmodified candidate is draft PR #513 commit
`20b26e433c1ab7150672d35f97a93f2cf4d88d94`.
The [Android run](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40203771523)
and [Python run](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40203771538)
on that exact head were rechecked and succeeded. No application code, Python
dependencies, mathematics, policy, test expectations or tolerances changed.

## Verification matrix

| Item | Status | Evidence / reason |
|---|---|---|
| Host Python tests | PASS | Fresh local suite: 626 passed and 18 subtests in 20.46 seconds, host CPython 3.14.4/NumPy 2.5.4/pandas 3.1.0. Current-head remote Python 3.11/3.12/3.13 regression and Ruff also succeeded. |
| Android-pinned host tests | PASS | Fresh local CPython 3.11.17/NumPy 1.26.2/pandas 2.1.3 suite: 623 passed, 1 optional Qt module skipped, 18 subtests, 3 pandas cast warnings, 19.60 seconds. Android itself uses packaged CPython 3.13, separately executed on the phone. |
| 4 KB Android runtime | PASS | Both physical S9+ variants passed all 11 required instrumentation tests; actual kernel page size 4096. Prior API 35 x86_64 evidence remains. |
| 16 KB Android runtime | PASS | Existing current-head API 35 x86_64 emulator evidence remains; the S9+ does not provide physical 16 KB coverage. |
| x86_64 runtime | PASS | Both page-size emulator jobs on current-head CI succeeded; not rerun locally in this phone check. |
| arm64 build | PASS | Both downloaded APKs contain arm64-v8a; fresh actual-payload audits each passed all 266 ELF libraries. |
| Physical arm64 runtime | PASS | Actual S9+ installation, packaged CPython 3.13/NumPy 1.26.2/pandas 2.1.3, exact parity, SQLite, policy/rescue/history, worker and navigation tests passed for both variants. |
| Manual portfolio and navigation | PASS | Both variants passed owned holding add/remove and all eight native destinations. |
| Background WorkManager behavior | PASS | Both variants passed fixture-backed worker/cadence/retry tests; release-derived APK also passed actual OS one-time work with a live network refresh. This does not establish elapsed periodic timing under battery restrictions. |
| Notification behavior | PASS | Actual Android notification submission and unchanged-state suppression passed on both variants. API 29 has no Android 13 POST_NOTIFICATIONS runtime-permission branch; that branch remains covered by existing emulator evidence. |
| Live provider on upgraded stack | PASS | Existing release APK probe passed in 13.843 seconds: OS work SUCCEEDED, scan status ok, changed scan key and at least 25 result rows through Android HTTPS and the packaged Python core. |
| Actual phone reboot persistence | PASS | Separately invoked seed and verify probes each passed around an authorized physical restart. Changed kernel boot IDs independently establish that a reboot occurred; rescue/history/outbox and the same active WorkManager UUID survived. |
| Phone/vendor Doze and battery behavior | NOT TESTED | The phone was USB-powered and tethering. No unplugged/overnight, natural Doze, OEM restriction or elapsed periodic delivery evidence is claimed. |
| Release signing | BLOCKED | Runtime candidate has the CI disposable debug signature. Production signing needs separately authorized owner credentials; no production key was created. |
| Play/distribution readiness | BLOCKED | Extended phone battery acceptance and production signing/distribution authorization remain open. No publishing started. |

## Exact parity and actual instrumentation

For both debug and AAB-derived release APKs, the unchanged suite reported
`OK (13 tests)`: 11 required passes and two explicit skips. The skips are the
opt-in live network probe and the separately invoked reboot probe. The live
probe was subsequently invoked explicitly and passed. The reboot probe's seed
and verify phases each also passed as a separate one-test invocation. In total,
the two variants and three explicit probe invocations produced 25 passes and
four intentional default-suite skips.

The frozen CLI comparisons remain exact for C, H1, H5, Blend, State, Stop, Buy,
GlyphSpec, policy action and reason codes. The same tests exercise persistent
rescue/history, notification transitions, retry identity, bridge transport,
portfolio editing and navigation. Kotlin contains no duplicate financial rules.

## Candidate identity and handling

Downloaded from the [successful current-head artifact](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40203771523/artifacts/12603445337).
Local SHA-256 checks match the prior successful emulator runtime evidence:

| APK | SHA-256 |
|---|---|
| Debug | `2c3479633e97c02010131284d521127fa96516ae5eb710cee973d0b609fe8e2f` |
| AAB-derived release validation | `d4023a64c868cf9bc9e711e468c91e4198eea8f79285bfa547726779f4b73233` |
| Instrumentation | `a11abbac5ed4aa61543b239d6ab776fda4db0c924b79d5213160d09cbb10f7c2` |

The compressed artifact ZIP digest is available from GitHub metadata, but is
not claimed as locally verified: `gh run download` extracted the contents.
Both actual APK native audits passed, independently of their metadata.

Package lookup found no prior Market Health installation. Tests installed the
fresh validation app; they did not clear an existing user database or uninstall
another application. No phone battery exemptions, global animation settings,
account credentials, production keys or financial definitions were changed.
The release-derived APK was installed over the debug APK using their shared
disposable CI validation signature.

The first startup waited while the phone was locked. Once unlocked, release
cold startup reported `Status: ok`, TotalTime 853 ms. This is one observation,
not an acceptance benchmark.

## Reproduction

Use the downloaded APKs above and select the actual phone explicitly with
`adb -s "$MH_DEVICE"`. Keep the phone unlocked during UI tests. Install the app
and matching instrumentation APK, then run:

```sh
adb -s "$MH_DEVICE" shell am instrument -w -r -e mhPageSize 4096 \
  dev.chrisdudley.markethealth.test/androidx.test.runner.AndroidJUnitRunner

adb -s "$MH_DEVICE" shell am instrument -w -r -e mhLiveProbe true \
  -e class 'dev.chrisdudley.markethealth.CoreParityTest#liveBackgroundWorkerRunsThroughThePackagedCore' \
  dev.chrisdudley.markethealth.test/androidx.test.runner.AndroidJUnitRunner
```

The emulator-only `run_runtime_checks.py` is not used on the phone. Its
unconditional Android 13 permission command does not apply to API 29; the
instrumentation itself correctly guards that permission branch by SDK level.
The live probe disables monitoring again in its cleanup.

For a separately authorized physical restart, invoke the existing
`RebootPersistenceTest#rescueHistoryAndPeriodicScheduleSurviveReboot` with
`-e mhRebootPhase seed`, record the kernel boot ID, reboot once, wait for boot
completion and the owner's unlock, then invoke the same test with
`-e mhRebootPhase verify`. Require distinct boot IDs and one pass in each phase.
This probe uses a separate QA SQLite file. It preserves the active periodic
request but deliberately leaves the application monitoring setting disabled;
request persistence alone does not prove a live periodic refresh after reboot.
The verify phase cancels its QA periodic request. Post-reboot cold startup
reported `Status: ok`, TotalTime 862 ms.

The first host invocations called each virtual-environment interpreter without
activating its PATH. Eight subprocess tests in each run exited 127 because their
default `JERBOA_PYTHON=python` executable was unavailable. Repeating each full
suite with `JERBOA_PYTHON` explicitly pointing to that same virtual-environment
interpreter passed, without changing source, fixtures or tolerances. Initial
failure logs remain in the local validation output; final passing logs are
retained with this report. The pinned host's three pandas cast warnings remain
visible and were not suppressed.

Raw test/startup logs, their SHA-256 values and a machine-readable verification
matrix are in [the retained evidence](evidence/physical-s9-2026-10-26/result.json).

Automatic coordinator polling and messaging remain canceled at the user's
request. This validation does not restart that workflow.
