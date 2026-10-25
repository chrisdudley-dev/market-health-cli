# Android release-readiness verification

This phase is in progress on draft PR #513. Android remains the final target.
The Python engine, MH Policy and frozen parity expectations are unchanged.
See [the native investigation](NATIVE_DEPENDENCIES.md) for all 40 original failures.

## Verification matrix

| Item | Status | Evidence / reason |
|---|---|---|
| Host Python tests | PASS | Full local host regression; final count in saved logs. |
| Android-pinned host tests | PASS | Full NumPy 1.26.2 / pandas 2.1.3 regression on host CPython 3.11; desktop UI optional. Android itself uses CPython 3.13. |
| 4 KB Android runtime | BLOCKED | New dependency stack awaiting CI runtime result; original stack previously passed. |
| 16 KB Android runtime | BLOCKED | Official image booted locally and reported 16384; application execution awaiting CI. |
| x86_64 runtime | BLOCKED | Final candidate needs both page-size runtime jobs. |
| arm64 build | BLOCKED | Native wheels inspected; final release build result outstanding. |
| Physical arm64 runtime | NOT TESTED | No physical phone has been used. |
| Background WorkManager behavior | BLOCKED | Candidate worker, constraints and reboot probes awaiting Android execution. |
| Notification behavior | BLOCKED | Candidate OS delivery/permission/deduplication tests awaiting Android execution. |
| Release signing | BLOCKED | Production signing credentials intentionally not created; unsigned/test-signed validation only. |
| Play/distribution readiness | BLOCKED | Runtime gates, physical ARM validation and manual release credentials remain; no publishing started. |

ELF/ZIP inspection is BUILD compatibility evidence. Only a successful packaged
Android execution counts as RUNTIME validation. A built arm64 APK is not a physical
arm64 runtime result. Host regression does not replace Android instrumentation.

The resumed local sandbox disallows localhost sockets: ADB reported `could not
install *smartsocket* listener: Operation not permitted`. The official 16 KB AVD
had already booted with PAGE_SIZE=16384 before that restriction. The remaining
app/runtime checks run on the repository's CI emulators instead.

## Signing infrastructure

No production private key is generated, stored or committed. Without signing inputs,
release builds produce an unsigned APK/AAB. Set all four environment variables only
for an explicitly authorized signing run: `MH_ANDROID_KEYSTORE`,
`MH_ANDROID_KEYSTORE_PASSWORD`, `MH_ANDROID_KEY_ALIAS`, `MH_ANDROID_KEY_PASSWORD`.
The keystore must be readable and outside the repository. Partial configuration
fails without logging credential values. `:app:requireReleaseSigning` rejects an
unsigned distribution attempt. The CI validation APK uses only the runner's
disposable Android debug key; that private key is not uploaded.

The native gate audits actual final APK/AAB payloads, including Python .imy assets.
CI injects a 4 KB ELF into the final unsigned release APK and requires assembleRelease
to fail with the ABI/library diagnostic, then rebuilds a clean artifact. Bundletool
is pinned to an official release digest and generates a validation APK from the AAB.
The AAB must request PAGE_ALIGNMENT_16K; the generated APK is independently audited
and signature-checked before Android runtime tests.

Nothing in this phase adds AI, Strike, Options Health, broker/bank access, account
credentials or order placement. The desktop prototype remains isolated.
