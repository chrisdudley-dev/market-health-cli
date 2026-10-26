# Android release-readiness verification

Physical arm64 runtime: PASS on Galaxy S9+ (Android 10/API 29, 4 KB).
Extended phone battery/Doze acceptance and production signing remain open.

The release-readiness baseline passed 2026-10-25 on draft
[PR #513](https://github.com/chrisdudley-dev/market-health-cli/pull/513).
Current tested candidate: `20b26e433c1ab7150672d35f97a93f2cf4d88d94`, whose
application/build code is unchanged from `20e432dae3c1059efbf446b41d7791d793d91f4f`.
On 2026-10-26, the user supplied a physical Galaxy S9+; both APK variants,
the live refresh probe and an authorized actual reboot passed. See
[the physical-device report and retained logs](PHYSICAL_S9_VALIDATION.md).
This update changes documentation/evidence only. Android remains the final
target; the CLI remains supported. General distribution is not approved.

## Verification matrix

| Item | Status | Evidence / reason |
|---|---|---|
| Host Python tests | PASS | Full local suite: 626 passed, 18 subtests passed. Remote Python 3.11/3.12/3.13 regression and Ruff all passed in [run 40201995075](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995075). |
| Android-pinned host tests | PASS | Full NumPy 1.26.2 / pandas 2.1.3 suite on host CPython 3.11: 623 passed, 1 optional Qt module skipped, 18 subtests passed, locally and in CI. Android uses CPython 3.13; host checks do not replace Android execution. |
| 4 KB Android runtime | PASS | API 35 x86_64 and physical Galaxy S9+ API 29 arm64-v8a, actual PAGE_SIZE=4096. Debug and AAB-derived release APKs each passed all 11 required instrumentation tests and startup; reboot probes passed. [Emulator evidence](evidence/runtime-4096.json), [phone evidence](evidence/physical-s9-2026-10-26/result.json). |
| 16 KB Android runtime | PASS | Official API 35 google_apis_ps16k x86_64 PAGE_SIZE=16384. Both APKs each passed all 11 required instrumentation tests and startup; reboot probe passed. [Evidence](evidence/runtime-16384.json). |
| x86_64 runtime | PASS | Packaged CPython 3.13, NumPy, pandas and Android/Python bridge executed on both kernels with exact CLI fixture parity. Jobs used 4096 MB RAM and KVM. |
| arm64 build | PASS | Debug/release APKs and release AAB include arm64-v8a and x86_64. All 266 actual ELF libraries pass the 16 KB audit in each artifact. No arm64 runtime execution is implied. |
| Physical arm64 runtime | PASS | Galaxy S9+ SM-G965U, Android 10/API 29: both APK variants passed exact parity, packaged runtime, SQLite/rescue/history, notifications, worker, portfolio and navigation. Release-derived live refresh and actual reboot also passed. Scope is this device/API/page size. |
| Background WorkManager behavior | PASS | Fixture-backed production worker execution, disabled monitoring, minimum cadence, retry identity and unique periodic request tested. Its UUID survived actual emulator reboot on both kernels. Connected-network constraints are configured; elapsed cadence under phone battery restrictions is not established. |
| Notification behavior | PASS | Actual Android permission denial/grant, OS submission, owned transitions and unchanged-state suppression passed on both APKs/kernels. Rescue-to-SELL history/outbox behavior persisted across reboot. |
| Phone/vendor Doze and battery behavior | NOT TESTED | Elapsed refresh/notification delivery under real phone restrictions remains hardware/manual acceptance. WorkManager timing is approximate. |
| Native ELF and APK ZIP compatibility | PASS | All 266 libraries pass on both ABIs; direct-mapped JNI entries are uncompressed and 16 KB ZIP-aligned. Nested Chaquopy .imy payloads are inspected. BUILD evidence only. |
| Automatic 16 KB release gate | PASS | Release APK/AAB assembly enforces actual-payload checks. CI injected a 4 KB ELF into the final APK and confirmed release failure with ABI/path diagnostics, then rebuilt clean artifacts. |
| AAB-to-APK validation | PASS | Checksum-pinned official bundletool 1.18.3 confirmed PAGE_ALIGNMENT_16K and generated a debug-signed universal APK. Official zipalign/apksigner and native audit passed before installation on both kernels. |
| Signing infrastructure | PASS | Unsigned build, external environment configuration, fail-closed partial inputs and disposable test signing verified. No production private key created or committed. |
| Release signing | BLOCKED | Owner-provided production credentials/manual authorization outstanding. Release APK/AAB are unsigned; runtime validation APK uses the runner's disposable debug key. |
| Play/distribution readiness | BLOCKED | Extended phone battery/Doze/manual acceptance and production signing/distribution credentials remain. No publishing or general release is claimed. |
| Live external-provider refresh on upgraded stack | PASS | Physical S9+ release-derived APK passed the explicitly enabled existing probe: actual WorkManager success, status ok, changed scan key and at least 25 result rows. Public-source probe remains separate from deterministic CI. |

ELF/ZIP inspection establishes BUILD compatibility. Only packaged application
execution establishes RUNTIME validation. A built arm64 APK is not a physical ARM
result. API 26 is the build minimum; runtime evidence covers API 35 emulators
and the API 29 physical S9+. Physical 16 KB runtime remains untested.

## Exact parity and regression scope

Financial Python source and frozen expectations are unchanged in this phase.
Kotlin retains UI/lifecycle/HTTPS/WorkManager/notification responsibilities and
contains no duplicated scoring or trading-policy formulas.

The full host suite covers CLI/core, policy, rescue state, SQLite history,
transitions/outbox and notifications. Android compares the same fixture with the
frozen CLI reference for **C, H1, H5, Blend, State, Stop, Buy, GlyphSpec, policy
action and reason codes**. Previously exact numeric comparisons retain zero
tolerance. No mismatch was accepted by changing formulas, expectations or tolerances.

Each default instrumentation invocation has 11 required passes and two explicit
skips: the optional live network probe and the phase-specific reboot probe.
The runner separately invokes the reboot probe to seed, reboots the emulator,
then invokes it to verify. Both explicit invocations pass on each emulator.
A fresh process verifies holdings/account/shares, rescue count, subsequent SELL,
history, outbox suppression and the WorkManager request. Worker execution uses
fixture transport through the same application/core operation; it does not
pretend public market data was fetched.

## Dependency and native audit

The original actual APK had 272 ELF libraries: **40 failed**. These were 19 NumPy
1.26.2 extensions per ABI, plus x86_64 OpenBLAS 0.2.20 build 5 and libgfortran 4.9
build 0, all with 0x1000 PT_LOAD alignment. Every failing library was matched by
SHA-256 to its exact source wheel. The full library/version/ABI/alignment/source/
availability table is in [NATIVE_DEPENDENCIES.md](NATIVE_DEPENDENCIES.md).

The selected stack keeps Chaquopy 17.1.0, NumPy 1.26.2 and pandas 2.1.3, upgrades
CPython 3.11.17 to 3.13.16, and selects inspected OpenBLAS 0.3.33 build 2 wheels
from Chaquopy's explicit upstream index. The new BLAS has no libgfortran dependency.
No NumPy functionality or financial mathematics was removed. All 12 wheel files
are URL/hash-locked and verified before offline pip installation for both ABIs.

The gate recursively reads actual APK/AAB archives, detects ELF by bytes rather
than filename, checks every PT_LOAD and APK JNI ZIP layout, and rejects malformed
or empty payloads. Diagnostics report ABI, archive path, segment alignment and
failures. Run independently with:

```sh
python3 android/tools/audit_native_pages.py path/to/app.apk --report native-pages.json
cd android
./gradlew -PmhPython=python3.13 :app:verify16kDependencies
```

## Remote CI and retained artifacts

Current candidate Android [run 40203771523](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40203771523)
and Python [run 40203771538](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40203771538)
completed successfully on `20b26e4`; their successful status was rechecked for
physical validation. The table and retained artifacts below preserve the earlier
successful [run 40201995021](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995021)
on unchanged application code `20e432d`.

| CI item | Status | Evidence |
|---|---|---|
| Python CI | PASS | [Run 40201995075](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995075): all three Python-version jobs. |
| Android host tests | PASS | Build job: full pinned suite, 623 passed / 1 skipped / 18 subtests. |
| Android build | PASS | Debug/test APK, unsigned release APK and release AAB built for both ABIs. |
| Android lint | PASS | lintDebug and lintRelease completed without fatal errors. Dependency/deprecation warnings remain non-fatal. |
| Emulator/instrumentation | PASS | Separate 4096/default and 16384/google_apis_ps16k jobs; both APK variants and reboot probes. |
| Artifact upload | PASS | Build artifact and both runtime artifacts uploaded. |
| 16 KB checks | PASS | Debug/release APK, AAB and AAB-generated APK audit; negative release-gate proof; actual 16 KB runtime. |

Download the [candidate and detailed build reports](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995021/artifacts/12602292091),
[4 KB logs](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995021/artifacts/12602696580)
and [16 KB logs](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40201995021/artifacts/12602790711).
CI artifacts expire 2027-01-23. The committed [CI snapshot](evidence/ci-release-readiness.json)
retains job/step status, verification log excerpts, URLs and archive digests.

Earlier `20e432d` candidate SHA-256 values, identical across its page-size jobs:

- Debug APK: `ff9e049767423901fe3bdcff21cadc47dfbddbda2b6c7f632b8fdaa55c299523`.
- AAB-derived release test APK: `4aa0f362a0b86a51e6d6e615ef443e71125d1ab60a62d4fc0c80712add4f2d91`.

Earlier failures remain visible and are not counted as passes.
[Run 40197840434](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40197840434)
exposed an assumed debug-keystore path; Gradle now supplies the actual path.
[Run 40198530608](https://github.com/chrisdudley-dev/market-health-cli/actions/runs/40198530608)
passed build gates but failed release instrumentation and 16 KB process execution.
The final commit makes the fixture bridge public across build types, captures
failure logcat and provisions 4096 MB emulator RAM. The succeeding full run above
is the evidence for this candidate; the earlier 16 KB crash's precise cause was
not established from its short failure log.

The resumed local sandbox denied localhost sockets, including ADB's listener
(`Operation not permitted`). Local app execution could not finish, although the
official 16 KB image had booted and reported 16384 before that restriction.
Remote CI supplied actual application/runtime validation. Successful CI logs also
contain transient emulator ADB/teardown messages; the runner independently requires
installation, test results, startup and reboot rather than provisioning alone.

## Signing and remaining manual gates

No production private key was generated, stored or committed. No tracked keystore
or private-key material is present. Without signing inputs, release outputs are
unsigned. Supply all four environment variables only for an authorized signing run:
`MH_ANDROID_KEYSTORE`, `MH_ANDROID_KEYSTORE_PASSWORD`, `MH_ANDROID_KEY_ALIAS`,
`MH_ANDROID_KEY_PASSWORD`. The readable keystore must be outside the repository.
Partial configuration fails without logging values. `:app:requireReleaseSigning`
rejects an unsigned distribution attempt. CI uses only the runner's standard
disposable debug key for validation; that private key is excluded from uploads.

Both candidate variants passed physical S9+ installation, exact fixture parity
and notification checks. The release-derived APK additionally passed live worker
refresh and actual reboot persistence, as scoped in the
[phone report](PHYSICAL_S9_VALIDATION.md). Extended elapsed background
delivery under real unplugged/Doze/vendor battery settings remains untested.
Production signing requires separately authorized owner credentials. These
remaining gates prevent a general-release claim.

This phase stops here. The desktop prototype stays isolated. No Strike, AI/model,
Options Health, brokerage, bank, account credentials, order placement or publishing
work is included.
