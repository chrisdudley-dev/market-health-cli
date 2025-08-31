# Market Health CLI

Color-coded, terminal-first dashboard for quick “sector union” reads across the US equity market. It scores each sector across six factor buckets (A–F) using lightweight market-data proxies (from Yahoo Finance via `yfinance`) and renders an overview + drill-down table in the terminal with [Rich](https://github.com/Textualize/rich).

> ⚠️ Educational tool only. This is not investment advice.

---

## Contents

- [What it does](#what-it-does)
- [Scores at a glance](#scores-at-a-glance)
- [Install](#install)
- [Quick start](#quick-start)
- [Generating live data (engine → JSON)](#generating-live-data-engine--json)
- [Running the UI](#running-the-ui)
- [JSON schema](#json-schema)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License](#license)

---

## What it does

- Pulls sector & benchmark data from Yahoo Finance with a polite, TTL-cached fetcher.
- Scores each sector across **A–F** categories (6 checks each; 0/1/2 points).
- Renders a terminal dashboard:
  - **Overview**: A–F totals per sector + grand total.
  - **Details**: chips for each check within every category.
- Works on Windows, macOS, Linux (PowerShell and Bash examples below).

---

## Scores at a glance

Each category contains six checks scored **0 / 1 / 2**. Higher is better.  
Color blocks show the % of the category’s maximum (0–12) and of the overall (0–72).

**Implemented today**

- **B – Trend & Structure**  
  Stacked MAs, relative strength vs SPY, BB mid reclaim, 20-day breakout, volume expansion, holding 20-EMA.

- **C – Position & Flow** *(proxy implementation)*  
  EM Fit (distance vs EMA20), OI/Flow (volume vs 20-day avg), Blocks/DP (dollar volume vs avg),  
  Leaders%>20D (sector leader breadth), Money Flow (Chaikin MF), SI/Days *(placeholder)*.

- **D – Risk & Volatility**  
  ATR% (14), IV% proxy (Bollinger width%), 20-day corr to SPY, Event Risk *(placeholder)*, Gap Plan *(placeholder)*, Sizing/RR.

- **E – Environment & Regime**  
  SPY trend, sector rank (5-bar return), own trend breadth, VIX regime, 3-day RS, Drivers *(placeholder)*.

- **A – Catalyst Health** *(simple proxies for now)*  
  News (1-day move / vol burst) + neutral placeholders for the rest.

- **F – Execution & Frictions**  
  Neutral placeholders (scored 1) pending rules.

---

## Install

```bash
# from project root
python -m venv .venv
# Windows PowerShell
. .\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt`:

```
pandas
numpy
yfinance
rich
```

> Tested with Python 3.10–3.12.

---

## Quick start

You can run the UI in **demo mode** (random scores) without fetching any data:

```bash
python market_ui.py --topk 3
```

Monochrome (no colors), useful for limited terminals:

```bash
python market_ui.py --mono
```

To use **real scores**, generate a JSON file with the engine and point the UI at it (next sections).

---

## Generating live data (engine → JSON)

The engine returns a list of sector objects (`compute_scores`).  
Use a one-liner to dump JSON.

### Windows PowerShell

```powershell
python -c "import json; from engine import compute_scores; print(json.dumps(compute_scores(), indent=2))" `
| Out-File -Encoding utf8 sectors.json
```

### macOS / Linux (bash/zsh)

```bash
python - <<'PY' > sectors.json
import json
from engine import compute_scores
print(json.dumps(compute_scores(), indent=2))
PY
```

Options you can pass to `compute_scores`:

```python
compute_scores(
    sectors=["XLK","XLF","XLY"],  # default is all 10 SPDR sectors
    period="1y",
    interval="1d",
    ttl_sec=300                   # yfinance cache TTL
)
```

---

## Running the UI

Point the UI to the JSON you just generated:

```bash
python market_ui.py --json sectors.json --topk 5
```

Auto-refresh the UI periodically (it re-reads the JSON each time):

```bash
# refresh every 60s
python market_ui.py --json sectors.json --watch 60
```

> Pair this with a scheduled job (or manual re-run) to regenerate `sectors.json` on the same cadence.

Filter to specific sectors:

```bash
python market_ui.py --json sectors.json --sectors XLK XLF XLY
```

Monochrome:

```bash
python market_ui.py --json sectors.json --mono
```

---

## JSON schema

The UI consumes an array like:

```json
[
  {
    "symbol": "XLK",
    "categories": {
      "A": { "checks": [ {"label": "News", "score": 1}, ... ] },
      "B": { "checks": [ {"label": "Stacked MAs", "score": 2}, ... ] },
      "C": { "checks": [ {"label": "EM Fit", "score": 1}, ... ] },
      "D": { "checks": [ {"label": "ATR%", "score": 2}, ... ] },
      "E": { "checks": [ {"label": "SPY Trend", "score": 1}, ... ] },
      "F": { "checks": [ {"label": "Trigger", "score": 1}, ... ] }
    }
  }
]
```

- Each category has exactly 6 checks.  
- Each check has a `label` (string) and `score` (0 / 1 / 2).

---

## How it works

**Files**

- `engine.py` – data fetching + scoring
  - **TTL cache**: avoids spamming Yahoo (keyed by `(symbol, period, interval)`).
  - **Robust columns**: handles yfinance’s MultiIndex and naming quirks.
  - **Category logic**: B (trend), C (position/flow proxies), D (risk/vol), E (environment), A/F placeholders.
- `market_ui.py` – terminal UI with Rich
  - Overview totals (per category and overall)
  - Details table with per-check chips
  - `--watch` tick will **re-read JSON** and redraw

**Benchmarks used**

- `SPY` for relative strength & correlation
- `^VIX` for regime
- Curated **sector leaders** list for the breadth proxy (edit in `engine.py`).

---

## Configuration

- **Sector list**: change `SECTORS_DEFAULT` in either file or pass `--sectors` to the UI.
- **Leaders for Category C**: edit `SECTOR_LEADERS` in `engine.py`.
- **Fetch window**: `period` / `interval` kwargs on `compute_scores`.
- **Cache TTL**: `ttl_sec` on `compute_scores`.
- **Thresholds**: all scoring cutoffs are in `engine.py` (search for comments next to each check).

---

## Troubleshooting

### PowerShell errors like `The '<' operator is reserved`
PowerShell doesn’t support bash “here-docs”. Use the **PowerShell** one-liner shown above (`python -c ... | Out-File ...`).

### “Cannot find reference 'download' / 'Ticker'”
Make sure you import **`yfinance as yf`** (not `import yf`). The code already does this.

### Qodana/IDE warnings “Too broad exception” / “shadows name”
These have been narrowed where it matters (network/parse surfaces). Remaining “shadow” notes inside small scopes are harmless but can be renamed if you prefer.

### Empty frames or NaNs
Yahoo occasionally returns sparse data (e.g., premarket). The engine falls back to neutral scores where input is missing to keep the UI usable.

### Rate limits
The engine staggers requests and caches results. If you pull many leaders at short intervals, keep `ttl_sec` ≥ 300.

---

## Roadmap

- **A**: Real catalyst feed (earnings, guidance, insider trades, news sentiment).
- **C**: True options/flow inputs (OI changes, block prints, short interest).
- **D**: Event calendar hookup + real IV instead of BB width proxy.
- **E/F**: Driver mapping & Execution rules (Trigger/Invalidation/Targets/Time Stop).
- **CLI**: Optional `engine_cli.py --out sectors.json --loop 300` to regenerate JSON automatically.
- **Tests**: Deterministic fixtures for scoring and UI snapshots.

---

## License

Add a `LICENSE` file of your choice (MIT is common for OSS tooling).  
Until then, consider this **All Rights Reserved**.

---

### Maintainer tips

- Keep the leaders list short (8–12 per sector) for fast breadth checks.
- If you add symbols, prefer ETFs or very liquid names to stabilize volume-based proxies.
- For Windows terminals, `--mono` is handy if colors look off.

---

Happy scanning 👀📈
