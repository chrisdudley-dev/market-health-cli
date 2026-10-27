# Natural battery/Doze acceptance — DEBUG APK

Preparation date: 2026-10-26. Acceptance result: **NOT TESTED** until an actual
bounded unplugged observation and post-idle comparison have completed.

This is explicitly **NATURAL BATTERY/DOZE ACCEPTANCE — DEBUG APK**. It cannot
establish natural idle acceptance of the release-derived artifact. The separate
[physical functional/parity report](PHYSICAL_S9_VALIDATION.md) remains valid for
both artifacts, including the release-derived APK.

## Authorized artifact change

The owner explicitly authorized one in-place update to the previously validated
debug APK. No application rebuild or production source change was performed.

| Artifact | SHA-256 |
|---|---|
| Previous release-derived APK | `d4023a64c868cf9bc9e711e468c91e4198eea8f79285bfa547726779f4b73233` |
| Original validated debug APK | `2c3479633e97c02010131284d521127fa96516ae5eb710cee973d0b609fe8e2f` |

Both APKs were inspected before installation: application ID
`dev.chrisdudley.markethealth`, versionCode 2, versionName 0.2.0-rc1, and matching
certificate SHA-256
`ea6e33886ce623d05aff786eb3dd9b7ae0178c5d13fc379b709aa644f3640dbe`.
Android accepted `install -r -t`; no uninstall, data clearing, downgrade flag,
root, replacement key, or protection bypass was used. The installed debug hash,
UID and original first-install timestamp were verified after the update.

The run was subsequently closed on 2026-10-27 with **FAIL — APPLICATION DEFECT
IDENTIFIED**: foreground UI reconciliation retained an old snapshot. The full
four-hour natural idle requirement was also not established. See the separate
[result](NATURAL_IDLE_DEBUG_RESULT.md); the preparation protocol below remains
as the record of what was intended.

The release APK is non-debuggable with backup disabled. Its private DB and
WorkManager DB were unavailable before replacement; a full byte comparison
across replacement is therefore unavailable. Release UI Portfolio/History/
Settings and OS scheduling were retained before installation. The same visible
state was verified after installation. An immediate debug snapshot, before
opening its UI, retained all nine application tables, including historical
rows. A second snapshot after ordinary navigation matched every table's row
hash and the WorkManager unique name/UUID. These checks are evidence of
preservation with the stated pre-update visibility limitation.

## Read-only observation

[`android/tools/observe_idle.py`](../../android/tools/observe_idle.py) uses
normal authorized debug `run-as` reads, hashes, and tar streaming. It never
invokes application APIs, instrumentation, notification APIs, job APIs, UI
input, package installation, force-stop, battery changes or Doze commands.
UI configuration is a separate, explicitly authorized setup action.

The collector copies only the application DB, WorkManager DB, their durable
WAL/journal sidecars, refresh-cycle preferences and prior reboot-proof
preferences. It requires matching device hashes before/after copying, matches
every archived byte to those hashes, rejects unexpected/missing archive paths,
and refuses to overwrite an existing evidence directory. An unstable copy is
retried at most three times and then rejected.

SQLite integrity and canonical table contents are read only on disposable
host copies, including committed WAL data. Source files are never opened with
SQLite. Volatile SHM read marks are excluded and recreated only locally. Typed
values, BLOBs, nulls and integer precision are retained. Hash stability proves
the copy interval; normal application/OS activity outside it is not attributed
to the collector.

Synthetic tests cover deterministic serialization, non-mutation, live WAL
visibility, unsafe paths, missing/changed files, unstable copies, refusal to
overwrite and the read-only device commands. No financial definitions or
frozen fixtures changed. The full host and Android-pinned regressions passed
after the collector was added; the 11 added tests also passed separately.

Raw databases, preferences, screen captures, network and OS battery history
contain private device information. They stay in a restricted local directory
outside Git. Only redacted summaries/hashes may be included in project reports.

```sh
python3 android/tools/observe_idle.py --adb "$MH_ADB" --serial "$MH_DEVICE" \
  --output "$MH_PRIVATE/new-baseline" --label debug-pre-idle
# After the owner reconnects the phone, use a NEW output directory:
python3 android/tools/observe_idle.py --adb "$MH_ADB" --serial "$MH_DEVICE" \
  --output "$MH_PRIVATE/new-post-idle" --label debug-post-idle
```

## Bounded acceptance protocol

1. Verify the authorized original debug APK hash and preserved state.
2. Use existing Settings UI to select 30m, enable monitoring and save. Preserve
   ownership, accounts, Net Liq and all notification selections.
3. Verify persisted settings and existing unique periodic work; retain its UUID,
   interval/generation/period count/attempt state, current cycles, scans, policy,
   rescue/history/outbox and battery/network/boot metadata.
4. Finish the read-only pre-idle baseline before requesting disconnection. Record
   real USB disconnection as the start; preparation and the earlier premature
   unplugged period do not count.
5. Leave the phone unplugged, with independent normal network, screen off and
   substantially still/untouched for approximately four hours. No persistent
   ADB, forced Doze, exemptions, global setting changes or repeated wakeups.
6. On reconnection, capture the same evidence BEFORE reopening the app. Compare
   work UUID, observed period counts, actual scan/cycle IDs and timestamps,
   failures/retries, SQLite integrity, rescue/history, ownership and outbox.
   Observe recovery after wake separately from work that ran unplugged.
7. Report battery start/end and actual unplugged interval from available OS/
   owner evidence. Characterize natural idle/Doze only if directly evidenced.
   A delayed WorkManager task alone is not an application defect.

There are currently zero owned holdings. An idle period without a genuine
owned-position transition cannot establish fresh notification delivery or
active rescue consumption. Check existing state integrity and absence of
unexplained/duplicate records; keep the earlier synthetic functional tests
separate. Do not create holdings or synthetic transitions to improve coverage.

Final natural-test status must be one of PASS — NATURAL BATTERY/DOZE ACCEPTANCE,
PASS WITH DOCUMENTED PLATFORM LIMITATION, FAIL — APPLICATION DEFECT IDENTIFIED,
or INCONCLUSIVE — NATURAL DOZE NOT OBSERVED, always accompanied by the explicit
DEBUG APK scope. No artifact switch after this test, signing, publishing,
production changes, Strike or other phase is authorized. Report to the
coordinator and stop. Automatic coordinator scheduling remains canceled.
