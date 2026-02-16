# positions.v1 (positions.v1.json)

This project uses a local cache file to represent current portfolio holdings in a normalized form.

Default path (Jerboa runtime):
- `~/.cache/jerboa/positions.v1.json`

Primary producers:
- `scripts/import_positions_tos_csv.py` (Thinkorswim CSV → positions.v1)
- future: Schwab broker adapter (M4)

Primary consumers:
- `market_health/market_ui.py` (read-only Positions panel)
- `scripts/jerboa/bin/jerboa-market-health-ui-export` (includes positions into market_health.ui.v1.json)

## Design goals

- **Local-only**: no secrets stored in repo; credentials remain outside repo.
- **Stable contract**: UI should not break if positions data is missing or partial.
- **Extensible**: allow adding broker-specific fields later without breaking consumers.

## Top-level shape

Required:
- `schema`: must be `"positions.v1"`
- `positions`: array of position objects

Recommended:
- `generated_at`: ISO-8601 timestamp when written
- `source`: metadata about where positions came from
- `summary`: small computed summary for UI/doctor scripts

## Position object

Required:
- `asset_type`: `"equity"` or `"option"` (allow `"other"` for future)
- `symbol`: string (ticker or option symbol representation)

Recommended (common):
- `qty`: number
- `avg_price`: number
- `mark_price`: number
- `market_value`: number
- `cost_basis`: number
- `unrealized_pl`: number
- `currency`: string (default `"USD"`)

Option-specific (recommended when asset_type == "option"):
- `underlying`: string
- `expiry`: string (YYYY-MM-DD)
- `strike`: number
- `right`: `"C"` or `"P"`

## Backwards compatibility

Consumers must tolerate:
- missing optional fields
- unknown extra fields (future extensions)
- empty positions list

Machine schema:
- `docs/schemas/positions.v1.schema.json`
