# Testing + fixture workflow

This repo uses a small set of **golden fixtures** to keep the UI contract and scoring stable over time.

## Local quality gates (same as CI)

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
```

If you are making a change that intentionally affects outputs, update the corresponding fixture(s) and commit them in the same PR.

## Regenerate UI contract signature

Updates:

- `tests/fixtures/expected/ui_contract.signature.tsv`

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
. .venv/bin/activate

python scripts/ui_export_ui_contract_v1.py --scenario bullish --out /tmp/ui_contract.json

python - <<'PY'
import json
from pathlib import Path

VOLATILE = {"asof","generated_at","updated_at","timestamp","ts"}
contract = json.loads(Path("/tmp/ui_contract.json").read_text(encoding="utf-8"))

def shape_signature(d):
    def walk(x, path=""):
        out = []
        if isinstance(x, dict):
            for k in sorted(x):
                if k in VOLATILE:
                    continue
                out += walk(x[k], f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            types = sorted({type(i).__name__ for i in x})
            out.append((path, f"list[{','.join(types)}]"))
            for i in x[:1]:
                out += walk(i, f"{path}[]")
        else:
            out.append((path, type(x).__name__))
        return out
    return [f"{p}\t{t}" for p,t in walk(d)]

sig_p = Path("tests/fixtures/expected/ui_contract.signature.tsv")
sig_p.write_text("\n".join(shape_signature(contract)) + "\n", encoding="utf-8")
print("OK:", sig_p)
PY
```

## Regenerate scoring regression snapshot (bullish sector totals)

Updates:

- `tests/fixtures/expected/sector_totals.bullish.json`

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
. .venv/bin/activate

python - <<'PY'
import json, os, tempfile, subprocess
from pathlib import Path
from shutil import copyfile

scenario = Path("tests/fixtures/scenarios/bullish/jerboa_cache")
out_p = Path("tests/fixtures/expected/sector_totals.bullish.json")

home = Path(tempfile.mkdtemp())
cache = home / ".cache" / "jerboa"
(cache / "state").mkdir(parents=True, exist_ok=True)

for f in scenario.glob("*.json"):
    copyfile(f, cache / f.name)
for f in (scenario / "state").glob("*.json"):
    copyfile(f, cache / "state" / f.name)

env = os.environ.copy()
env["HOME"] = str(home)
env["QUIET"] = "1"
env.setdefault("JERBOA_PYTHON", "python")

subprocess.run(
    ["bash", "scripts/jerboa/bin/jerboa-market-health-ui-export"],
    check=True,
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

contract = json.loads((cache / "market_health.ui.v1.json").read_text(encoding="utf-8"))
sectors = contract.get("data", {}).get("sectors") or []

def total(s: dict) -> int:
    cats = s.get("categories") or {}
    t = 0
    if isinstance(cats, dict):
        for cat in cats.values():
            if not isinstance(cat, dict):
                continue
            for chk in (cat.get("checks") or []):
                if isinstance(chk, dict) and isinstance(chk.get("score"), int):
                    t += chk["score"]
    return int(t)

totals = {s["symbol"]: total(s) for s in sectors if isinstance(s, dict) and isinstance(s.get("symbol"), str)}
out_p.write_text(json.dumps(dict(sorted(totals.items())), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("OK:", out_p)
PY
```

## Adding new fixtures

- Prefer deterministic inputs checked into `tests/fixtures/scenarios/...`.
- Keep fixture generators as small scripts (or python snippets) and document them here.

## Onboarding an additional non-US market

Use the first Japan slice as the template for future market onboarding.

1. Add a market profile under `config/markets/`.
2. Add symbol metadata under `config/symbols/global_markets.yaml`.
3. Reuse or extend taxonomy/family config under `config/taxonomy/`.
4. If the market should become executable in scoring, wire the symbol into the active universe and any required leaders mapping.
5. Verify metadata and export coverage with:
   - `tests/test_market_catalog_v1.py`
   - `tests/test_engine_market_metadata_v1.py`
   - `tests/test_ui_export_global_market_metadata_v1.py`
   - `tests/test_non_us_market_slice_smoke_v1.py`

Recommended local refresh/export sequence:

    PYTHONPATH=$PWD python3 scripts/export_environment_v1.py
    PYTHONPATH=$PWD python3 scripts/export_ohlcv_sectors_v1.py
    PYTHONPATH=$PWD python3 scripts/export_forecast_scores_v1.py --source ~/.cache/jerboa/ohlcv.sectors.v1.json
    PYTHONPATH=$PWD python3 scripts/ui_export_ui_contract_v1.py

Success criteria for a newly onboarded market:
- symbol is present in `market_health.sectors.json`
- symbol metadata is present in `market_health.ui.v1.json`
- forecast/export artifacts remain readable
- canonical `mh` UI still renders without regressions
