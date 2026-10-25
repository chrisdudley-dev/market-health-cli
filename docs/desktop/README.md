> Historical desktop prototype documentation. Android is the final target; see `docs/android/ARCHITECTURE.md`. Earlier install/build commands below describe the superseded prototype.

# Market Health desktop

`market-health-desktop` launches the native PySide6 application. All portfolio
information stays in a local SQLite database. No account connection or order
execution implementation is included.

## Install and launch from source

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[desktop]'
market-health-desktop
```

On Windows, activate `.venv\Scripts\activate` instead. The eight screens cover
Dashboard, Portfolio, Trading List, Buy Candidates, Market Health, History, Policy,
and Settings. Use **Refresh Now** for live scores; refreshing runs off the UI thread.
Select a table row to inspect every exact rule comparison and GlyphSpec check audit.
Resize the divider to expand the explanation panel.

In Portfolio choose **Mark Owned**, enter the symbol, shares, and an account label.
Account names are editable and created locally. Cost basis is per share. Edit a row
or clear Owned to remove it. Shares can be fractional or zero; the explicit manual
Owned record, rather than a share threshold or a scan bullet, determines ownership.
Refresh after changing ownership to compute the appropriate entry/maintenance policy.

Settings accepts Net Liq and optional cash. Target positions defaults to eight.
The explanation panel shows Net Liq / target and floor(slot / current price), using
Buy only if a current price is absent. Position sizing never changes eligibility.

The original engine configuration remains available through its environment flags,
including `MH_ENABLE_ETF_UNIVERSE=1` for its configured broader ETF registry.
Inverse symbols use the existing inverse-universe configuration and are not screened
out by the retired replacement constraints. Optional manually owned symbols are
included in live scans even when outside the configured universe.

## Policy interpretation

The app enforces the constants and comparisons in `policy/constants.py` and displays
those same constants in Policy. SELL comparisons take precedence over normal HOLD.
H5=C satisfies HOLD before the overlapping WATCH rule. Other uncovered neutral
combinations show UNKNOWN and explain the gap; no additional trading rule is inferred.
Unowned symbols that fail the BUY gate show UNKNOWN / not BUY. Raw percentage scores
are evaluated without rounding away an edge; the table can show decimals.

A rescue streak persists through restarts and data errors. It clears on a successful
normal evaluation or when the final local holding for that symbol is removed. Editing
shares or inspecting a position does not consume a refresh. A repeated import of the
same snapshot is idempotent. Repeated live refreshes are separate refresh events,
including when daily bars are unchanged, as specified by the two-refresh rule.

## Monitoring and local notifications

Enable Background Monitoring to run the refresh timer at 5/10/15/30/60 minutes.
With a supported system tray, closing the window hides it; choose Open Market Health
or Quit from the tray menu. Without a tray, monitoring continues while the main window
is open. The timer does not hard-code market hours.

Owned notifications require a change from a previous valid action. Initial scans,
unchanged actions, UNKNOWN, and DATA ERROR do not generate owned action notifications.
Optional BUY notifications occur only on a false-to-true qualification transition.
Snapshot input is historical and never sends notifications. The SQLite outbox records
pending/submitted/unavailable delivery. Qt confirms submission to the operating system,
not that a popup was displayed; OS notification preferences still apply.

A failed refresh records a failed scan, marks the old view STALE, and creates no new
policy decision from unavailable data. Partial scans store DATA ERROR for affected
symbols and preserve their previous valid action and rescue count. Last refresh and
price bar timestamps are both visible. A successful refresh older than the configured
refresh interval is marked STALE, even with monitoring disabled.

## Storage, logs, and history

Default application data directory:

- Linux: `${XDG_DATA_HOME:-~/.local/share}/market-health`
- macOS: `~/Library/Application Support/MarketHealth`
- Windows: `%LOCALAPPDATA%/MarketHealth`

`market-health.sqlite3` contains holdings, account labels, settings, scan history,
append-only decisions and transitions, rescue state, ownership audit events and
notification history. Schema version is stored in SQLite `user_version`. Newer
unknown schemas are rejected. Structured JSON logs rotate under `logs/`.
Back up this directory with the app closed. `--database PATH` selects an isolated
local database for testing. No prior brokerage cache is imported automatically.

History filters by symbol, UTC date, action, and account as recorded at decision time.
Use Export filtered history JSON for a local audit export.

## CLI compatibility

```sh
market-health --refresh --pi-grid
market-health --database my-test.sqlite3 --snapshot docs/desktop/example-snapshot.json
market-health --out policy-history.json
market-health --demo --pi-grid
python -m market_health --out current-checks.json
python -m market_health.market_ui --json current-checks.json --pi-grid
```

The installed terminal commands still work. Live policy CLI and desktop share
`engine_api.py`, the same refresh service, policy engine, and local database.
The original raw check exporter and Rich demo/offline renderer remain available.
Legacy linked recommendation exports fail with a migration message. Retired behavior
and superseded tests are listed in `RETIRED.md`; preserved numerical engines are
listed in `ARCHITECTURE.md`.

## Packaging

```sh
python -m pip install -e '.[desktop,build]'
python -m market_health.desktop.build
```

The output is `dist/MarketHealth/`. Distribute the whole directory; launch
`MarketHealth` on Linux or `MarketHealth.exe` on Windows without a Python command.
The application icon and a Linux `.desktop` launcher template are in `packaging/`.
Set the template's Exec and Icon to the installed absolute paths before installing it
in `~/.local/share/applications`. Build independently on each target OS. Linux builds
require a compatible glibc and native Qt display libraries. macOS distribution needs
normal app signing/notarization; this Linux build has not been validated there.

PyInstaller's directory bundle was chosen for easy inspection and predictable startup.
It includes only Qt Widgets/Core/Gui dependencies needed by this application; no web
server is introduced. See the official [PyInstaller usage guide](https://pyinstaller.org/en/stable/usage.html)
and [Qt system tray reference](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html).

## Verification

```sh
python -m pip install -e '.[desktop,dev]'
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m ruff check .
python -m ruff format --check .
QT_QPA_PLATFORM=offscreen dist/MarketHealth/MarketHealth --database /tmp/mh-smoke.sqlite3 --smoke-test
```

The example snapshot contains illustrative policy inputs, not actual quotes. To inspect
it in isolation, pass both `--snapshot docs/desktop/example-snapshot.json` and a separate
`--database` path. It does not prepopulate holdings in your normal portfolio.
