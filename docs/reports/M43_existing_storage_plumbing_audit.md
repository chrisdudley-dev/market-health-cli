# M43 Existing Storage / Snapshot / Alert Plumbing Audit

Issue: #319  
Milestone: M43 Raspberry Pi Market-Health Alert Service  
Status: Audit classification  
Runtime target: Debian/Raspberry Pi  
Development/control surface: Android Termux over remote.it SSH  

## Purpose

Audit existing database, snapshot, alert, state, ledger, history, Telegram, Google Drive, Google Sheets, backup, and systemd-related plumbing before adding new M43 storage or alert-service code.

M43 should not blindly create a second storage system without understanding what already exists.

## Summary recommendation

M43 should not start by adding an unrelated second alert/storage stack.

The repo already contains several pieces directly relevant to M43:

- existing SQLite-backed ledger plumbing,
- a JSONL ledger exporter,
- a cooldown policy module with tests,
- snapshot-first refresh and UI contract plumbing,
- an existing Telegram status-change notifier prototype,
- existing Jerboa refresh/status/alert shell entrypoints,
- existing user-level systemd service/timer templates,
- scenario fixtures and tests suitable for deterministic CI.

Recommended path:

1. Reuse the existing refresh-all, positions-refresh, UI-export, and systemd patterns.
2. Adapt the existing ledger/SQLite work into a dedicated M43 alert-service database layer.
3. Adapt the existing cooldown policy for alert duplicate suppression.
4. Adapt or replace the Telegram v0 script with a proper M43 notifier module supporting disabled, dry-run, test, and live modes.
5. Do not delete legacy/prototype files in this audit issue.
6. Open implementation PRs only after this audit report is merged.

## Classification legend

- reuse: trustworthy existing plumbing that M43 should build on directly
- adapt: useful existing plumbing that needs changes before M43 can use it
- deprecate: old plumbing likely superseded by M43, but not deleted in this issue
- ignore: unrelated match
- unknown: needs more review

## Candidate files found

| File | Classification | Notes |
|---|---:|---|
| `market_health/ledger.py` | adapt | Existing SQLite-style ledger module. Useful proof of persistence plumbing, but M43 likely needs a dedicated alert-service schema. |
| `scripts/export_ledger_jsonl_v0.py` | adapt | Useful backup/export pattern for future alert history exports. |
| `market_health/cooldown_policy.py` | adapt | Strong candidate for M43 duplicate suppression and alert cooldown behavior. |
| `market_health/refresh_snapshot.py` | adapt | Existing snapshot-first cache/UI plumbing. Useful for understanding current artifacts. |
| `market_health/ui_triscore_ascii.py` | adapt | Snapshot-first UI contract behavior. Useful for mapping M43 snapshot fields. |
| `market_health/dashboard_legacy.py` | adapt | Reference for held-position fields such as score, H1/H5, State, Stop, Buy, SupATR, and ResATR. M43 should not scrape terminal output. |
| `scripts/export_recommendations_v1.py` | reuse | Existing recommendation artifact exporter. |
| `scripts/export_forecast_scores_v1.py` | reuse | Existing forecast-score artifact exporter. |
| `scripts/ui_export_ui_contract_v1.py` | reuse | Existing UI contract export path. |
| `scripts/jerboa/bin/jerboa-market-health-refresh-all` | reuse | Existing repaired refresh-all entrypoint. This should be the first refresh path called by M43 v1 unless later work proves otherwise. |
| `scripts/jerboa/bin/jerboa-market-health-positions-refresh` | reuse | Existing positions refresh entrypoint. |
| `scripts/jerboa/bin/jerboa-market-health-refresh` | reuse | Existing market-health refresh entrypoint. |
| `scripts/jerboa/bin/jerboa-market-health-ui-export` | reuse | Candidate artifact source for M43 snapshots. |
| `scripts/jerboa/bin/jerboa-market-health-status` | adapt | Candidate base or reference for `mh_alert_status`. |
| `scripts/jerboa/bin/jerboa-market-health-alert` | unknown | Existing alert entrypoint must be reviewed before deciding whether to adapt or supersede. |
| `scripts/telegram_notify_on_status_change_v0.py` | adapt | Existing Telegram prototype. M43 needs safer modes, secret handling, delivery logging, and alert formatting. |
| `docs/examples/telegram.json.example` | adapt | Useful example, but M43 should define a production-safe local secrets contract. |
| `scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.service` | reuse | Existing user systemd service template. |
| `scripts/jerboa/systemd/user/jerboa-market-health-refresh-all.timer` | reuse | Existing user systemd timer template. |
| `scripts/jerboa/systemd/user/jerboa-market-health-refresh-all-failure.service` | adapt | Useful pattern for failure/system-health behavior. |
| `scripts/jerboa/systemd/user/jerboa-market-health-ui.service` | adapt | Relevant if M43 consumes UI contract artifacts. |
| `scripts/jerboa/install_market_health.sh` | adapt | Existing install/update pattern. M43 should follow conventions but avoid surprising production installs. |
| `scripts/jerboa/doctor_market_health.sh` | adapt | Useful pattern for M43 doctor/status checks. |
| `tests/fixtures/scenarios/*/jerboa_cache/*.json` | reuse | Existing deterministic cache fixtures. M43 CI should use fixtures, not live market data. |
| `tests/fixtures/scenarios/*/jerboa_cache/state/market_health_refresh_all.state.json` | reuse | Useful for stale-data and system-health tests. |
| `tests/test_cooldown_policy.py` | reuse | Existing cooldown test coverage. |
| `tests/test_ledger_v0.py` | adapt | Existing SQLite persistence test pattern. |
| `tests/test_export_ledger_jsonl_v0.py` | adapt | Existing JSONL export test pattern. |
| `tests/test_telegram_notify_status_change_v0.py` | adapt | Existing Telegram test pattern. |
| `tests/test_ui_contract_v1.py` | reuse | Existing UI contract coverage. |
| `tests/test_ui_contract_required_fields_v1.py` | reuse | Existing UI contract field coverage. |
| `.github/workflows/ci.yml` | reuse | M43 tests should integrate into existing CI. |
| `.github/workflows/release.yml` | ignore | Not directly relevant to M43 alert runtime unless packaging changes are introduced later. |
| `docs/reports/m42_stop_buy_code_path_audit.md` | reuse | Useful style/reference for audit reports. |
| `docs/examples/market_health.ui.v1.example.json` | reuse | Useful fixture/reference for M43 snapshot mapping. |
| `docs/recommendations.v1.md` | reuse | Existing recommendation contract documentation. |
| `docs/schemas/recommendations.v1.schema.json` | reuse | Existing recommendation schema. |
| `market_health/brokers/schwab_oauth.py` | adapt | Relevant to freshness, but OAuth repair is separate from this storage audit. |
| `scripts/schwab_oauth_walkthrough.py` | adapt | Useful operator reference for separate Schwab freshness work. |
| `config/symbols/global_markets.yaml` and `config/taxonomy/*.yaml` | ignore | Market taxonomy files, not storage/alert plumbing for this issue. |

## Storage path recommendation

Use a dedicated M43 SQLite database for alert-service state under the existing Jerboa cache/state area rather than inside the repo.

Recommended future implementation shape:

- database: `~/.cache/jerboa/market_health_alerts.v1.sqlite`
- config: `~/.config/jerboa/market_health_alerts.toml` or the repo's established config format
- secrets: local-only file under `~/.config/jerboa/`, never committed
- logs: journald for systemd runs plus SQLite `runs` and `system_events` rows

The existing `market_health/ledger.py` proves SQLite-style plumbing exists, but M43 should not assume the old ledger schema is the right schema for alert snapshots, delivery status, cooldown state, system-health events, and daily digests.

## Migration and compatibility concerns

- Do not delete or rewrite existing ledger code in this audit PR.
- Do not change refresh-all behavior in this audit PR.
- Do not change Telegram behavior in this audit PR.
- Do not make CI depend on live market data.
- Do not make CI depend on Telegram network access.
- Avoid terminal-dashboard scraping; consume existing JSON/cache/UI contract artifacts instead.
- Keep Android/Termux as development/control only.
- Keep production scheduling on Debian/Raspberry Pi.
- Keep systemd behavior run-once oriented for v1.
- Treat Schwab/OAuth freshness as related but separate from the storage audit unless it directly affects snapshot source selection.

## Recommended follow-up issues

This audit supports the current M43 issue order:

1. #320 — Debian/Raspberry Pi runtime and deployment contract
2. #321 — SQLite schema and storage layer
3. #322 — held-position market-health snapshot collector
4. #323–#326 — alert detectors and cooldown suppression
5. #327 — Telegram notifier modes
6. #328 — run-once alert command
7. #330–#332 — systemd, status command, and runbook

## Acceptance criteria status

- [x] Search the repo for existing storage/snapshot/alert/state/history/notification plumbing
- [x] Create `docs/reports/M43_existing_storage_plumbing_audit.md`
- [x] List each relevant file found
- [x] Classify each file as `reuse`, `adapt`, `deprecate`, `ignore`, or `unknown`
- [x] Recommend the M43 storage path
- [x] Identify migration or compatibility concerns
- [x] Do not delete old plumbing in this issue unless it is clearly obsolete and covered by tests
- [x] Keep this issue primarily audit/report focused
