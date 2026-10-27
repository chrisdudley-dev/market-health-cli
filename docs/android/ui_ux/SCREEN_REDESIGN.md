# Screen changes

Dashboard leads with the count of saved result rows, distinct owned symbols, last recorded successful scan, all-symbol action distribution, manual Net Liq, qualifying unowned candidates, monitoring and the three latest persisted transitions. It does not claim every attempted symbol calculated or rank economic changes.

Market Health, Trading List and Buy Candidates share searchable score cards and display-only action/ownership/problem filters. Score sorting orders existing numeric values with missing values last. Trading List remains owned symbols. Buy Candidates remains unowned plus `result.buy_qualified`, irrespective of any UI action chip.

Symbol detail is a full scrollable destination. It separates score summary, price/Stop/Buy/State, exact engine checks/reasons, rescue/sizing and expandable exact numeric/GlyphSpec audit. Current detail resolves its symbol against the latest state on each update. A historical selection retains its original recorded decision and explicitly identifies observation-time ownership; current sizing is not invented for history.

Portfolio presents account positions, exact shares, optional cost basis, current scores/action and saved refresh time. Add/Edit reuse the existing bridge payload. Edits retain the original symbol/account key. Failed saves keep the form open with its draft; removal requires a named holding/account confirmation and supports cancellation.

History displays original previous→new actions, exact reasons and recorded score summaries in a timeline. A single-symbol point chart and accessible exact table describe loaded observations. Filter requests preserve symbol/action/account/date and pagination; nothing infers a missing cause.

Policy preserves every original paragraph and the numbered owned-position ordering directly from Python `policy_text()`. Card spacing makes the existing rules readable without copying threshold constants into Kotlin. Notification explanation describes existing transitions and duplicate suppression.

Settings groups local appearance, approximate 15/30/60-minute monitoring, notification switches/permission, manual sizing inputs and source/build details. Appearance saves separately from authoritative SQLite. Operational settings still pass through the existing settings service and scheduler.

Every screen retains saved results while refresh is in progress. Explicit loading, no-refresh, no-holdings, no-history, no-candidates, offline, error and stale states distinguish absence and failure from a fresh successful result. Toolbar and pull-to-refresh invoke the same guarded ViewModel operation.
