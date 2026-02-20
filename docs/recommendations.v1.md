# recommendations.v1 (recommendations.v1.json)

## Purpose
`recommendations.v1` is the **machine-readable** recommendation artifact produced by the rotation/recommendations pipeline. It represents a single v0 decision:

- **SWAP**: replace a current holding with a better candidate (given constraints)
- **NOOP**: take no action (with an explicit reason)

This contract is designed so the UI can render decisions without re-computing logic.

## Location
- `~/.cache/jerboa/recommendations.v1.json` (primary cache artifact)

## Producer / Consumer
- Produced by: refresh pipeline (M8.4/M8.5)
- Consumed by: UI exporter (M8.6) → embedded into `market_health.ui.v1.json`

## Required fields
Top-level:
- `schema`: must be `"recommendations.v1"`
- `asof`: ISO timestamp of the input snapshot
- `recommendation`: the decision object

Decision object (`recommendation`) always includes:
- `action`: `"SWAP"` or `"NOOP"`
- `reason`: human-readable summary
- `horizon_trading_days`: integer (T+H)
- `target_trade_date`: `YYYY-MM-DD` or `null` (filled once trading-day semantics are available)
- `constraints_applied`: list of constraint names applied (may be empty)

## SWAP fields
When `action = "SWAP"`, also includes:
- `from_symbol`
- `to_symbol`

## Examples
- SWAP: `docs/examples/recommendations.v1.swap.json`
- NOOP: `docs/examples/recommendations.v1.noop.json`

## Schema
- `docs/schemas/recommendations.v1.schema.json`
