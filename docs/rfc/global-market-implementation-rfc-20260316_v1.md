# RFC: Global Market Implementation Backbone (v1)

Status: Draft
Date: 2026-03-16
Owner: Christopher

Related milestones:
- #31 Sprint 1 - Global Backbone + Japan Broad Market
- #32 Sprint 2 - Japan Sectors + Diversity v1

Related issues:
- #190 through #203

## Summary

This RFC proposes a scalable global-market backbone for `market-health-cli`.

Japan is the first pilot market.

The implementation will preserve the current core contracts:
- A-E scoring model
- 6 checks per dimension
- forecast outputs: C / H1 / H5 / blend
- recommendation outputs: SWAP / NOOP

The new work will be added through:
- market metadata
- symbol catalog expansion
- market-aware scoring and forecast context
- diversity-policy upgrades
- existing UI/export wiring

## Sprint 1 goal

Deliver one stable non-US vertical slice using a Japan broad-market symbol.

Done means the symbol can be:
- refreshed
- scored
- forecasted
- exported
- rendered in the UI
- considered by the recommendation engine

without regressions to the current US universe.

## Sprint 2 goal

Add representative Japan sectors and diversity v1 for mixed US/JP exposure.

## Core decision

Do not create separate engines for Japan.

Use the existing program flow and extend it with:
- market profile metadata
- symbol metadata
- taxonomy bridge
- diversity metadata

## Diversity v1

Use a static overlap model:
- same bucket + same market = strongest overlap
- same family + same region = high overlap
- same family + different region = moderate overlap
- different family + different region = lower overlap

## Recommendation

Proceed in this order:
1. global-market metadata backbone
2. Japan broad-market vertical slice
3. stabilize scoring, forecast, recommendation, and UI integration
4. add a small Japan sector sleeve
5. validate diversity v1
6. only then consider a second country
