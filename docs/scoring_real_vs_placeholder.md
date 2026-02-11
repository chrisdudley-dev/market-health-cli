# Scoring: Real vs Placeholder Inputs (Guardrail)

This repository supports optional/paid/external inputs via **provider boundaries**.
If a provider is **not configured**, the system returns `status=no_provider` and **must not** imply confidence.

## Category D (IV + Event Calendar)
- **IV (`iv.v1`)**
  - Stub provider: `docs/examples/iv_stub.sample.json`
  - Real provider: **not implemented yet**
  - Guardrail: When `status != ok`, treat IV contribution as **0** and annotate UI as “missing”

- **Calendar (`calendar.v1`)**
  - Stub provider: `docs/examples/calendar_stub.sample.json`
  - Real provider: **not implemented yet**
  - Guardrail: When `status != ok`, treat calendar contribution as **0** and annotate UI as “missing”

## Standard statuses
- `ok` — real/stub data present and normalized
- `no_provider` — boundary exists but nothing configured; do not imply signal
- `error` — provider misconfigured or crashed; do not imply signal; surface `errors[]`
