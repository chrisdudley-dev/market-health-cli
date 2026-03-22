# Advanced level families for v2

Date: 2026-03-22

## Decision
No-go for v1. Keep the current v1 structure stack centered on existing clustered support/resistance, ATR-normalized cushion/overhead, breakout/breakdown/reclaim triggers, and risk overlay fields.

Go for limited v2 exploration only after calibration work is complete.

## Candidate features reviewed

### 1. Volume confirmation
Examples:
- breakout with above-baseline volume
- breakdown with above-baseline volume
- reclaim confirmation with expanding participation

Expected benefit:
- may reduce false breaks
- may improve confidence ranking for breakout/reclaim states

Expected cost:
- adds sensitivity to data quality and session handling
- increases calibration burden
- raises ambiguity for thin or irregular symbols

Recommendation:
- v2 candidate
- not required for v1

### 2. Anchored VWAP / event-anchored levels
Examples:
- anchored VWAP from recent swing high/low
- anchored VWAP from gap or event markers

Expected benefit:
- may improve context for reclaim and overhead interpretation
- potentially useful as an additional confluence source

Expected cost:
- anchor selection policy must be deterministic
- anchor choice can become subjective without strong rules
- higher implementation and testing complexity

Recommendation:
- v2 research candidate
- do not add to v1

### 3. Volume-profile style level families
Examples:
- HVN/LVN-style zones
- acceptance/rejection around high-participation areas

Expected benefit:
- could improve zone quality in range-bound instruments
- may add useful context for support/resistance clustering

Expected cost:
- data and windowing complexity
- heavier implementation surface
- harder to explain cleanly in CLI

Recommendation:
- backlog / later v2 candidate
- not for current v2 entry set until simpler items are calibrated

### 4. Diagonal / trendline-derived levels
Expected benefit:
- may catch structure missed by purely horizontal clustering

Expected cost:
- strong subjectivity risk
- difficult to keep deterministic and explainable
- high false-precision risk in terminal presentation

Recommendation:
- no-go for current roadmap

### 5. Options/open-interest or dealer-positioning-derived levels
Expected benefit:
- may help explain pinning or resistance/support behavior in some names

Expected cost:
- external data dependency
- substantial complexity and freshness burden
- poor fit for current lightweight offline-first workflow

Recommendation:
- no-go for current roadmap

## Benefit vs cost summary

### Highest-value next candidate
1. Volume confirmation

Why:
- clearest potential improvement to breakout/breakdown confirmation
- easiest to explain in existing structure language
- integrates naturally with risk overlay confirmation logic

### Second candidate
2. Anchored VWAP / event-anchored levels

Why:
- useful additional confluence source
- potentially compatible with existing weighted structure clustering

### Defer
- volume-profile families
- diagonal/trendline levels
- options/open-interest-derived levels

## Go / no-go recommendation

### For v1
No-go.

Reason:
v1 is already scoped around deterministic, explainable, terminal-friendly structure artifacts. Adding advanced families now would increase complexity before calibration and validation are complete.

### For v2
Go, but only for:
1. volume confirmation
2. anchored VWAP / event-anchored levels

Gate:
- only after calibration/backtest work clarifies current baseline behavior
- only with deterministic rules and explicit fallback behavior
- only if CLI output remains concise

## Suggested follow-on sequence
1. finish calibration/backtest work for current structure stack
2. prototype volume confirmation as sidecar-only evidence
3. evaluate anchored VWAP as an optional weighted source
4. keep other advanced families in backlog unless strong evidence appears
