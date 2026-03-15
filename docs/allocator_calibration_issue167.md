# Allocator Calibration for Issue #167

This note compares allocator behavior in two modes:

- **SGOV-only**: precious-metals candidates are excluded from the candidate set
- **SGOV-plus-metals**: precious-metals candidates are included, with existing
  portfolio constraints such as max one precious holding and GLTR overlap blocking

## Comparison inputs

The deterministic comparison inputs come from:

- `tests/fixtures/allocator_scenarios_issue166.v1.json`

These scenarios cover:

- weakest held below floor -> SGOV
- weakest held below floor -> GLTR
- precious to SGOV
- SGOV to metal
- second precious holding blocked
- candidate fails delta

## Recommended defaults

Keep the current defaults:

- `min_floor = 0.55`
- `min_delta = 0.12`

## Justification

These defaults are recommended because they:

1. keep weak absolute candidates out of the portfolio,
2. prevent marginal churn,
3. still allow clearly superior precious-metals candidates to beat SGOV fallback,
4. preserve constraint-driven behavior in blocked precious-holding cases.

## Follow-up

No immediate follow-up tuning issue is recommended.

A follow-up should be opened only if broader real-world scenario coverage shows:
- SGOV fallback is too sticky, or
- precious-metals candidates win too often on marginal improvements.
