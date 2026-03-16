# Allocator Rules for SGOV and Precious Metals

## Definitions
- `weakest_held`: currently held position with the lowest blended score
- `weakest_score`: blended score of `weakest_held`
- `best_candidate`: highest-scoring eligible replacement candidate
- `best_score`: blended score of `best_candidate`
- `min_floor`: minimum absolute blended score required to buy a candidate
- `min_delta`: minimum improvement required over `weakest_held`

## Rules
1. Score all supported assets in the active universe.
2. Identify `weakest_held` and `weakest_score`.
3. Build the eligible candidate set from supported non-held assets.
4. Exclude policy-blocked candidates.
5. Filter candidates by `best_score >= min_floor`.
6. Rank remaining candidates by blended score.
7. If `best_score - weakest_score >= min_delta`, recommend `weakest_held -> best_candidate`.
8. If no candidate clears both floor and delta, use `SGOV` as fallback policy asset.
9. Enforce `max_precious_holdings = 1`.
10. Block `GLTR` plus single-metal overlap in v1.

## Examples
- `XLB 0.43 -> XLE 0.61` with floor `0.55` and delta `0.12` => `SWAP`
- `XLB 0.41 -> GLTR 0.58` with floor `0.55` and delta `0.12` => `SWAP`
- `XLK 0.44`, no candidate `>= 0.55` => `SGOV fallback`
- `XLP 0.50 -> GLTR 0.58` with delta `0.08 < 0.12` => `SGOV fallback`
- `GLTR` already held and `PALL` is best candidate => reject second precious holding unless replacing existing precious holding

## Initial Defaults
```yaml
allocator:
  min_floor: 0.55
  min_delta: 0.12
  sgov_symbol: SGOV
  sgov_is_policy_fallback: true
  max_precious_holdings: 1
  block_gltr_component_overlap: true
```
