# forecast_scores.v1

Purpose: deterministic, explainable forecast scoring artifact computed at **T** for horizons **T+H**.

## Envelope
- `schema`: `"forecast_scores.v1"`
- `asof`: ISO datetime string
- `horizons_trading_days`: list[int]
- `scores`: `{ SYMBOL -> { H -> payload } }`

## Per-symbol per-horizon payload
- `forecast_score`: float in [0,1]
- `points`: int
- `max_points`: int
- `categories`: A–E
  - each category has exactly **6** checks:
    - `label` (string)
    - `meaning` (string)
    - `score` (0/1/2)
    - `metrics` (object)
- `diagnostics`: object (optional)
