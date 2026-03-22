# Structure contribution against hold/swap outcomes

Date: 2026-03-22

## Purpose
Evaluate whether structure adds useful signal to hold/swap reasoning, and document the current conclusion for the v1/v2 roadmap.

## Chosen test set
This baseline uses the repo's scenario fixtures as the current deterministic evaluation set:

- `tests/fixtures/scenarios/bullish`
- `tests/fixtures/scenarios/sideways`
- `tests/fixtures/scenarios/bearish`

These scenarios are the current stable proxy set available inside the repo for repeatable recommendation-path review.

## Evaluation focus
The review is centered on forecast-mode recommendation output and the structure sidecar fields now exposed in the active path.

## Metrics documented
For each scenario, inspect and compare:

1. Primary decision contract
- recommendation action (`SWAP` / `NOOP`)
- weakest held symbol
- best candidate symbol
- selected pair

2. Pairwise decision metrics
- robust edge
- weighted robust edge
- average edge
- veto reason, if present

3. Structure sidecar contribution
- support cushion ATR
- overhead resistance ATR
- state tags
- candidate-pair structure reason tags
- watch-level trigger visibility
- risk-overlay / execution-guidance sidecars

4. Judgment criteria
- does structure improve explanation quality for the chosen pair?
- does structure improve risk visibility for held positions?
- does structure justify changing the primary action contract today?

## Result summary
Current conclusion: structure is valuable today primarily as an explanatory and monitoring layer, not yet as a proven replacement for the existing primary hold/swap decision contract.

Observed outcome from the current scenario baseline:
- structure materially improves readability of candidate-pair reasoning through deterministic short tags
- structure materially improves held-position monitoring through watch levels, execution guidance, and risk overlay sidecars
- the primary recommendation contract remains appropriately separate from these structure signals
- current repo evidence is still insufficient to justify changing core recommendation weights solely from this baseline

## Decision
For v1:
- keep structure as sidecar/explanatory context
- keep `SWAP` / `NOOP` as the primary action contract
- do not claim calibrated action-weight improvement yet

For roadmap:
- this issue is satisfied as a baseline backtest/review note with chosen test set, documented metrics, and written result summary
- further calibration or regime-conditioned weighting remains follow-on work and stays tracked separately

## Follow-on implication
`#246` remains open because regime-conditioned and symbol-family-specific weighting still lacks terminal-visible proof in the active recommendation path with documented overrides and fallback behavior.
