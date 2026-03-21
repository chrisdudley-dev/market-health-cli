# Floor/Ceiling RFC — E0 Freeze

## Tracking
- PR: #248
- Issue: #226 Freeze v1 structure fields and semantics
- Issue: #227 Resolve engine module naming and import paths
- Issue: #228 Define CLI structure sidecar rendering contract

## Frozen v1 structure artifact

### Required fields
- version
- symbol
- as_of
- price
- nearest_support_zone { lower, center, upper, weight }
- nearest_resistance_zone { lower, center, upper, weight }
- support_cushion_atr
- overhead_resistance_atr
- breakout_trigger
- breakdown_trigger
- reclaim_trigger
- breakout_quality_bucket
- breakdown_risk_bucket
- catastrophic_stop_candidate
- state_tags

### Optional fields
- tactical_stop_candidate
- stop_buy_candidate
- support_cushion_sigma
- overhead_resistance_sigma
- support_confluence_count
- resistance_confluence_count
- notes

## Canonical modules
- market_health/structure_engine.py
- market_health/engine.py
- market_health/recommendations_engine.py
- market_health/forecast_recommendations.py
- market_health/risk_overlay.py

## CLI rendering contract

### Compact tri-score table
- remove or hide Δ1
- remove or hide Δ5
- add SupATR
- add ResATR
- optional State

### Held-position detail widgets
1. Recommendation (cached)
2. Risk Overlay
3. Watch Levels / Structure
4. Optional Execution Guidance

### Candidate-pair rows
- short structure-aware reason tags only
- no raw structure number dump in v1

## Working rule
No issue is considered done until branch/PR checks are green.
Final integration will merge back into `pi-grid` with squash merge.
