# Category A (Events/Catalysts) provider boundary

Goal: introduce a clean boundary for catalysts/news/events so the core scorer/UI can consume a **normalized** model
without hard-coding vendor logic into the engine.

## Rules
- **Degrade gracefully** when no provider is configured (status=`no_provider`, points=[]).
- **No secrets in repo**; provider configuration lives under `~/.config/jerboa/`.
- Prefer **cache-first** patterns: providers should refresh into `~/.cache/jerboa/` on a cadence and the UI reads cache.

## Normalized event model (events.v1)
Each event point should include:
- `ts` (ISO-8601 string)
- `type` (e.g., macro/earnings/news/filing/analyst/etc.)
- `headline` (short human-readable text)
- `impact` (0..1 recommended)
- `confidence` (0..1 recommended)

## Caching strategy (recommended)
- Write provider output to: `~/.cache/jerboa/events.v1.json`
- Store `generated_at` and `source` metadata for debugging.
- Refresh interval should be conservative by default (e.g., 10–30 minutes) and configurable.
- Keep a small “failure bundle” on errors (timestamped) to support troubleshooting.

## ToS / rate limits
When adding a real provider:
- Respect vendor rate limits and Terms of Service.
- Avoid scraping if prohibited; prefer official APIs.
- Keep credentials local-only and rotate/revoke on suspicion.
