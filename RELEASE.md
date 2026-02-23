# Release process

## Pre-flight
- [ ] CI green on `pi-grid`
- [ ] `python -m ruff format --check .`
- [ ] `python -m ruff check .`
- [ ] `python -m pytest -q`

## Versioning
- [ ] Ensure `market_health.__version__` resolves correctly in editable + installed modes
- [ ] Decide tag (e.g., `v0.1.0`)

## Tag + push
```bash
git checkout pi-grid
git pull --ff-only
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

## GitHub Release checklist
- [ ] Create a GitHub Release for the tag
- [ ] Title: `vX.Y.Z`
- [ ] Notes: summarize user-visible changes
- [ ] (Optional) Attach artifacts/screenshots

## Post-release
- [ ] Verify install from source works
- [ ] Verify `python -m market_health.market_ui --pi-grid` runs
- [ ] Verify exporter writes `~/.cache/jerboa/market_health.ui.v1.json`

