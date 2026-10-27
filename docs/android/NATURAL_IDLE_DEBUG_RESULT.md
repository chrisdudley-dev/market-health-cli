# Natural battery/Doze result — DEBUG APK

**FAIL — APPLICATION DEFECT IDENTIFIED**

Scope: **NATURAL BATTERY/DOZE ACCEPTANCE — DEBUG APK**. Run closed 2026-10-27.
The defect is foreground UI reconciliation, not financial mathematics or policy.
The original candidate and evidence were preserved before any UI refinement.

## Reproducible finding: ANDROID-UI-RESUME-001

After normal resume of the existing Activity, its status still read
`STALE · OK · 2026-10-26T08:10:19.318Z`. A read-only snapshot taken before opening
the app established that authoritative SQLite already contained a successful
25-symbol result at `2026-10-27T08:35:20.253Z`. The old screen persisted on a
second UI observation. Normal Android Back followed by reopening the same APK
displayed `OK · 2026-10-27T08:35:20.253Z`, without manual refresh, force-stop,
installation or a new calculation.

The existing ViewModel reloads in its initializer; the Activity has no resume
reconciliation and background writes do not update the ViewModel's state flow.
An existing Activity can therefore keep rendering its old snapshot. The stale
warning is visible, but fresh persisted data is not adopted automatically.
This needs a presentation/lifecycle fix and a regression test on a separate
branch. No fix was applied to the acceptance candidate.

## What the background run establishes

The identical unique periodic work UUID survived, still configured for 30
minutes. Its period count increased from 8 to 48. The archive contains 40 new
successful live scans, each with 25 decisions, and 17 failure records for
unavailable required SPY/VIX data followed by recovery. The latest persisted
work-cycle token matches the latest successful scan. Exact initial transport
causes are not retained; a provider/network root cause is not asserted.

Both SQLite integrity checks pass. All pre-existing scans, decisions,
transitions and notifications are present and unchanged. Accounts, holdings,
settings and portfolio-event hashes match the baseline. The 40 successes have
distinct scan keys; all history/outbox relationships are valid. Latest policy
actions match their persisted decisions. No new notifications or transitions
were generated; all four prior notifications retain their submitted status.
There are zero owned holdings, so this run does not exercise a new owned
transition or active rescue consumption. Earlier functional tests remain
separate evidence for those behaviors.

## Natural idle and battery limits

The conservative disconnection reference was 2026-10-26 06:32:30 Eastern, after
the completed baseline. The earliest intended endpoint was 10:32:30 Eastern.
Retained OS idling history shows brief light-idle/maintenance periods, unlock
interruptions, and return to charging at approximately 09:11:52 Eastern—before
that endpoint. Only five successful scans and two errors lie between the
conservative reference and that recorded charging event. The 35 later successes
are not counted as unplugged execution.

Deep idle is not present in retained history. No forced Doze, exemption or
global battery-setting change was used. The four-hour continuous natural idle
requirement is not established. Wall-clock time until the next-day snapshot is
not a substitute. Endpoint battery was 100% while USB-powered, and retained
batterystats history resets at 04:41 local on 2026-10-27. Unplugged battery drain
cannot be recovered; **100% → 100% is not a zero-drain result**. No reason for
the history reset is invented.

| Check | Status | Evidence / limit |
|---|---|---|
| Periodic work persistence/recovery | PASS | Same UUID, 40 additional periods/successful scans; recovered after errors. |
| Foreground reconciliation | FAIL | ANDROID-UI-RESUME-001 reproduced on normal resume and Back/reopen. |
| Four-hour natural battery acceptance | NOT TESTED | Required continuous interval not established. |
| Natural light idle | PASS | Retained light-idle/maintenance events. |
| Natural deep Doze | NOT TESTED | No retained deep-idle event. |
| SQLite/history/outbox integrity | PASS | Hash/prefix/link/uniqueness and integrity checks. |
| New owned notification delivery | NOT TESTED | No owned holding or natural policy transition. |
| Release-derived natural idle | NOT TESTED | This run used the DEBUG artifact only. |

## Artifact and evidence preservation

The installed original debug APK still hashes to
`2c3479633e97c02010131284d521127fa96516ae5eb710cee973d0b609fe8e2f`.
It is the previously physically validated API 29 arm64/4 KB candidate from
`20b26e433c1ab7150672d35f97a93f2cf4d88d94`; production application source remains
unchanged from `20e432dae3c1059efbf446b41d7791d793d91f4f`.
The prior [release-derived functional/parity/live/reboot evidence](PHYSICAL_S9_VALIDATION.md)
remains valid and separate. No release-APK natural-idle result is claimed.

The test-only collector has 11 passing synthetic tests; preparation regressions
passed 637 host and 634 Android-pinned tests, with inherited subtests, optional
Qt collection skip and existing pandas warnings. Ruff format/check passed.
No production code changed afterward and no new app build was performed.

[Machine-readable result and private-input hashes](evidence/natural-idle-debug-2026-10-27/result.json)
retain the redacted comparison. Raw DBs, preferences, screenshots, battery and
network diagnostics remain in restricted local storage outside Git. Retained
crash-buffer records contain no app-named crash; API 29 does not provide a
complete historical exit-info guarantee.

The next authorized UI phase can address reconciliation on its dedicated
branch after coordinator reporting. It must preserve this failed candidate's
evidence and must not relabel natural battery acceptance as passed. No further
physical test, artifact switch, production signing or publishing was performed.
