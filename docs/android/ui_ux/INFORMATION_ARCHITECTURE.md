# Information architecture

Four frequent destinations receive compact navigation: Dashboard, Market Health, Portfolio and History. All eight existing destinations remain available in a scrollable navigation drawer, including Trading List, Buy Candidates, Policy and Settings. Larger windows use a navigation rail for the frequent destinations. Do not put eight items into a phone bottom bar.

Market Health, Trading List and Buy Candidates share one renderer while retaining their different existing membership predicates. Search/action/ownership/problem filters and numeric sorting affect presentation only. Missing score values sort last; no score, policy, universe or recommendation is derived by sorting.

Selecting a current symbol identifies it by symbol and rereads the latest UI snapshot when that snapshot changes. Selecting a historical decision retains that recorded decision and clearly labels its observation time; current data must not silently replace a historical decision.

Portfolio entries retain symbol/account identity, shares, optional cost basis and notes. Add/edit send the same bridge payloads, including original identity on edits. Removal requires an explicit confirmation. Cancel never removes a holding.

History retains server-side symbol/action/account/UTC-date filtering and before_id pagination. Charts are an additional view of those persisted observations, not a substitute for the decision timeline or a reconstructed historical dataset.

Policy renders the original rule descriptions and order directly from the bridge. GlyphSpec, raw numeric precision, reason codes, source timestamps and technical metadata live in expandable audit sections.

Settings group appearance, manual sizing inputs, monitoring cadence, notification controls, data status and build information. Theme changes are appearance-only; saving monitoring preserves Android's approximate cadence semantics.
