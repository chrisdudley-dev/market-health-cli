# UI contract: market_health.ui.v1.json

The UI is driven by a single JSON contract file written to:

- `~/.cache/jerboa/market_health.ui.v1.json`

This contract is intended to be stable. Breaking changes should be accompanied by a contract version bump and updated tests/fixtures.

## Top-level keys

Required:
- `schema` (string)
- `asof` (string timestamp)
- `meta` (object)
- `summary` (object)
- `data` (object)

Optional:
- `generated_at` (string timestamp)
- `status_line` (string, legacy/compat)

Note: some historical schema strings may be prefixed (e.g. `jerboa.market_health.ui.v1`).

## meta (cache artifact metadata)

`meta` contains cache-file descriptors. Each entry is an object with at least:

Required:
- `path` (string)
- `exists` (boolean)

Common optional fields:
- `bytes` (int)
- `mtime` (int)
- `schema` (string) depending on artifact type

Expected entries:
- `environment`
- `positions`
- `sectors`
- `state`
- `recommendations`
- `events_provider`

## summary (rollups + statuses)

`summary` is small and stable; it contains counts and status flags used by the UI.

Required:
- `positions_count` (int)
- `events_count` (int)
- `recommendations_status` (string; one of `ok`, `missing`, `unreadable`)

Optional (may not be present in all exporters):
- `sectors_count` (int)
- other rollups

## data (payload for the UI)

Required payload keys used by the UI:
- `environment` (object)
- `positions` (object)
- `sectors` (array)
- `state` (object)
- `recommendations` (object)

Additional common payload:
- `dimensions_meta` (object; A-F label metadata)
- `categories_meta` / `dimensions_meta` at top-level may exist for compatibility

## Example contract JSON

See: `docs/examples/market_health.ui.v1.example.json`

## Contract stability tests

- Required fields/types: `tests/test_ui_contract_required_fields_v1.py`
- Shape signature: `tests/fixtures/expected/ui_contract.signature.tsv`
- Scoring regression snapshots: `tests/fixtures/expected/sector_totals.*.json`

Regeneration steps are documented in `docs/TESTING.md`.
