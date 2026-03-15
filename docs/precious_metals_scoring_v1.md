# Precious Metals Scoring v1

## Scope
This document defines the initial A-E scoring behavior for precious-metals ETFs:
- GLDM
- SIVR
- PPLT
- PALL
- GLTR

## v1 policy
Precious metals must remain directly comparable with sector and inverse ETFs:
- same A-E dimensions
- same 6 checks per dimension
- same 0/1/2 quantization
- same normalized output shape for downstream recommendation logic

## A-D behavior
For v1, precious metals reuse the shared scoring logic for:
- A Announcements
- B Backdrop
- C Crowding
- D Danger

Rationale:
- these dimensions are broad enough to remain comparable
- v1 favors structural consistency first
- later versions may specialize internals without changing the output contract

## E behavior
Dimension E contains sector-oriented assumptions. In v1:
- SPY Trend: shared
- Sector Rank: neutralized to 1 for precious metals
- Breadth: neutralized to 1 for precious metals
- VIX Regime: shared
- 3-Day RS: shared
- Drivers: shared for now

Rationale:
- Sector Rank and Breadth are explicitly sector-specific
- neutralization preserves comparability without forcing false sector semantics onto metals

## Notes
- GLTR is treated as a precious basket ETF
- v1 does not yet add metal-specific data providers
- recommendation logic still consumes the same normalized score structure
