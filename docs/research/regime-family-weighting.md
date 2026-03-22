# Regime-conditioned and symbol-family-specific weighting

Date: 2026-03-22

## Purpose
Document the active forecast recommendation weighting model used for blended current/H1/H5 utility display and diagnostics.

## Calibration source
The active default source is `calibration.v1`.

`market_health/calibration_v1.py` now exports a `weighting` section containing:
- `base_utility_weights`
- `regime_overrides`
- `symbol_family_overrides`

## Default fallback behavior
If no regime or family override applies, the system falls back to the base utility weights:

- `C = 0.50`
- `H1 = 0.25`
- `H5 = 0.25`

This preserves the existing default contract.

## Regime-conditioned overrides
Supported regime keys:
- `neutral`
- `risk_on`
- `risk_off`
- `sideways`

These overrides adjust blend emphasis without removing the default fallback path.

## Symbol-family-specific overrides
Supported deterministic family buckets:
- `generic_equity`
- `sector_etf`
- `broad_index`
- `metals`
- `rates`

A family can be inferred from symbol or supplied explicitly via `symbol_family_by_symbol`.

## Active-path behavior
The forecast recommendation path resolves effective utility weights per symbol by:

1. starting from base utility weights
2. applying any regime override
3. applying any symbol-family override
4. normalizing the final weights

The active recommendation diagnostics now record:
- `weighting_regime`
- `weighting_profile_source`
- `symbol_families`
- `effective_utility_weights_by_symbol`

## Current conclusion
This change satisfies the weighting-contract requirement by making regime-conditioned and symbol-family-specific weighting explicit, deterministic, documented, and fallback-safe in the active forecast recommendation path.
