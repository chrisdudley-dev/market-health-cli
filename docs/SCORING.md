# Scoring (A-F) and A/C/D upgraded inputs

This project computes sector "Market Health" using 6 dimensions (A-F). Each dimension contains a fixed set of checks, and each check produces a non-negative integer score. Totals are sums of check scores.

## Dimensions

- A (Narrative): news / analysts / events / insiders / peers-macro / guidance context.
- B (Trend): trend-structure signals (MAs, relative strength, breaks).
- C (Flow): positioning/flow style signals (OI/flow, blocks, leadership breadth).
- D (Risk): risk/volatility inputs (ATR/IV/correlation/event risk/sizing).
- E (Regime): macro/regime drivers (SPY trend, sector rank, breadth, VIX).
- F (Plan): execution plan checks (trigger/invalidation/targets/time stop, etc).

## Safe fallbacks (default behavior)

By default, scoring uses built-in proxies and safe fallbacks:
- Missing data for a dimension yields reasonable defaults (no crashes).
- The output shape stays stable (no schema changes).

## A/C/D upgraded inputs (feature-flagged)

The engine supports optional per-check overrides for A, C, and D using extra columns present in the *latest row* of the sector dataframe (`df_sym`). This is behind environment flags so behavior is unchanged unless you opt in.

Enable flags:
- `MH_FEATURE_A_V1=1`
- `MH_FEATURE_C_V1=1`
- `MH_FEATURE_D_V1=1`

When enabled, if an override column exists, its numeric value is coerced to an integer score and replaces the corresponding check score for that label. If the column is missing/invalid, the original proxy score is preserved.

### A override columns (label -> candidate columns)
- News -> `a_news`, `news_score`, `news`
- Analysts -> `a_analysts`, `analysts_score`, `analysts`
- Event -> `a_event`, `event_score`, `event`
- Insiders -> `a_insiders`, `insiders_score`, `insiders`
- Peers/Macro -> `a_peers_macro`, `peers_macro_score`, `peers_macro`
- Guidance -> `a_guidance`, `guidance_score`, `guidance`

### C override columns (label -> candidate columns)
- EM Fit -> `c_em_fit`, `em_fit_score`, `em_fit`
- OI/Flow -> `c_oi_flow`, `oi_flow_score`, `oi_flow`
- Blocks/DP -> `c_blocks_dp`, `blocks_dp_score`, `blocks_dp`
- Leaders%>20D -> `c_leaders_20d`, `leaders_20d_score`, `leaders_20d`
- Money Flow -> `c_money_flow`, `money_flow_score`, `money_flow`
- SI/Days -> `c_si_days`, `si_days_score`, `si_days`

### D override columns (label -> candidate columns)
- ATR% -> `d_atr_pct`, `atr_pct_score`, `atr_pct`
- IV% -> `d_iv_pct`, `iv_pct_score`, `iv_pct`
- Correlation -> `d_corr`, `corr_score`, `corr`
- Event Risk -> `d_event_risk`, `event_risk_score`, `event_risk`
- Gap Plan -> `d_gap_plan`, `gap_plan_score`, `gap_plan`
- Sizing/RR -> `d_sizing_rr`, `sizing_rr_score`, `sizing_rr`

## Missing data handling

- If the dataframe is empty, proxy checks are used.
- Overrides are applied only when enabled and the override column exists and is numeric.
- Overrides do not introduce new fields; they only update scores for existing labels.
