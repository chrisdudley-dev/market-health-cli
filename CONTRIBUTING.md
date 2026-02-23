# Contributing

## Setup
```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Quality gates
Before opening a PR:
```bash
python -m ruff format .
python -m ruff check .
python -m pytest -q
```

## Testing philosophy
- Prefer deterministic fixtures for cache-backed behavior.
- Keep the UI contract stable; update golden signatures intentionally.

## PR guidelines
- Keep PRs focused and small.
- Reference issues with `Fixes #NN`.
- Include updated fixtures/signatures only when schema/output changes.

