# Market Health Android UI/UX

Implementation is complete on android/ui-ux-refinement for coordinator review. The required resume/history fix passed its separate gate at 54937ab before visual changes began; see RESUME_RECONCILIATION.md. The failed physical candidate remains preserved, and natural battery acceptance remains open.

The visual direction uses quiet teal accents, distinct surfaces, readable numeric summaries and visible freshness. All eight destinations remain. Screens render authoritative C/H1/H5/Blend, State, Stop, Buy, GlyphSpec, policy, reasons, rescue, ownership and sizing; they do not calculate those values.

Dashboard emphasizes the last recorded successful refresh, latest attempt/data status, actual symbol count, owned-symbol and policy summaries, monitoring, and recent recorded transitions. Market Health uses compact cards with four score displays, search and display-only filters/sorting. Details separate the current/historical observation, scores, price levels, exact explanation/checks, rescue/sizing and technical audit.

Trading List remains exactly the owned-symbol subset. Buy Candidates remains exactly unowned rows whose authoritative result.buy_qualified is true. The renderer must not substitute its own score thresholds or action-based approximation for those existing predicates.

History is a dated decision timeline with original previous/new actions and reasons. Single-symbol score charts plot recorded points only, using actual observation timestamps, with no smoothing or interpolation. Missing values remain missing and are available in an accessible table. Time windows apply only to loaded history with sufficient time coverage.

The only bridge addition is optional ui_metadata version 1: a read-only query for the last scan recorded as status=ok, plus the three newest recorded transitions joined to their original decisions. This prevents guessing that a partial result is a complete success. No schema, financial mathematics, policy, persistence writes, history/outbox rules or frozen fixtures change. Tests prove empty/missing states, exact historical linkage and unchanged DB bytes.

Theme preference is local presentation storage separate from authoritative SQLite. Manual ownership/account labels and settings continue through the existing bridge. Refresh/pull-to-refresh uses the same CoreRepository.refresh path. Foreground reconciliation only rereads persisted data and never initiates a quote fetch or calculation.

No Strike placeholder, model dependency, chat, brokerage, bank or order feature is introduced. New UI candidates are exercised on disposable emulators, not automatically installed over the preserved S9+ artifact.

Visual/test/performance evidence and explicit manual limitations are recorded in FINAL_UI_UX_REPORT.md and evidence/verification.json.
