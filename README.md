# Market Health CLI

A terminal-first, color‑coded dashboard that summarizes sector “market health” at a glance.  
Built with [Rich](https://github.com/Textualize/rich) and designed to look great on a Raspberry Pi.

> Educational tool only — not investment advice.

---

## Highlights

- **Pi Grid**: ultra-compact, single‑grid view for small displays (e.g., Raspberry Pi).
- **Color coding**: intuitive heat-style backgrounds from **weak → strong**.
- **Live or offline**: fetches data via `yfinance`, or render from a local JSON file.
- **Zero-friction demo**: generate realistic demo data with `--demo`.

---

## Quickstart (run locally)

```bash
# Create and activate a virtual environment (Windows PowerShell shown)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the compact Pi grid with demo data (auto-fit columns)
python market_ui.py --demo --pi-grid --grid-cols 0
```

### Live data (no demo)
```bash
python market_ui.py --pi-grid --grid-cols 0
```
> Requires internet access; data is pulled via `yfinance`.

---

## Raspberry Pi notes

On Raspberry Pi, using the community **piwheels** index speeds up installation for heavy packages like NumPy/Pandas:

```bash
# Optional: use piwheels for much faster installs on Raspberry Pi
export PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt

# Compact grid tuned for small screens
python market_ui.py --pi-grid --grid-cols 0 --watch 30
```

You can fine‑tune the grid density by changing `--grid-cols` (e.g., `--grid-cols 4`).  
Use `--mono` for a monochrome look (no colors).

---

## CLI usage

`market_ui.py` controls what you see in the terminal. The most useful flags:

| Flag | Type / Default | What it does |
| --- | --- | --- |
| `--pi-grid` | `bool` | Show the compact single‑grid (best for Pi screens). |
| `--grid-cols` | `int` (default **4**; use **0** to auto‑fit) | Number of columns in the grid. |
| `--demo` | `bool` | Use generated demo data. |
| `--json` | `str` | Load data from a JSON file instead of live fetch. |
| `--sectors` | `list[str]` | Override default sector tickers (e.g., `--sectors XLK XLF XLV`). |
| `--topk` | `int` (default **3**) | In the standard (non‑grid) view, show details for the top‑K sectors. |
| `--mono` | `bool` | Monochrome output (no color). |
| `--watch` | `int` | Auto‑refresh every _N_ seconds. |
| `--period` | `str` (default **1y**) | `yfinance` lookback period (e.g., `6mo`, `1y`). |
| `--interval` | `str` (default **1d**) | `yfinance` interval (e.g., `1d`, `1h`). |
| `--ttl` | `int` (default **300**) | In‑process cache TTL (seconds) for live fetch. |

Examples:

```bash
# Minimal Pi grid with auto-fit columns
python market_ui.py --pi-grid --grid-cols 0

# Demo grid with a fixed 4‑column layout
python market_ui.py --demo --pi-grid --grid-cols 4

# Standard view with details (no grid)
python market_ui.py --sectors XLK XLF XLY XLV
```

---

## Rendering from JSON

You can render without fetching live data by pointing to a JSON file:

```bash
python market_ui.py --json scores.json --pi-grid --grid-cols 0
```

**JSON format** (per sector), roughly:

```json
[
  {
    "symbol": "XLK",
    "A": [{"label": "News", "score": 2}, {"label": "Analysts", "score": 1}],
    "B": [{"label": "..." , "score": 0}], 
    "C": [{"label": "..." , "score": 2}], 
    "D": [{"label": "..." , "score": 1}], 
    "E": [{"label": "..." , "score": 1}], 
    "F": [{"label": "..." , "score": 0}]
  }
]
```

To generate `scores.json` yourself using the compute engine:

```bash
# Module form
python -m market_health.mh_cli --out scores.json

# Or script form
python market_health/mh_cli.py --out scores.json
```

Then render it:
```bash
python market_ui.py --json scores.json --pi-grid --grid-cols 0
```

---

## Project layout (key files)

```
market_health/           # scoring engine and CLI
  engine.py              # computes category checks from price data
  mh_cli.py              # writes scores.json (yfinance)
market_ui.py             # terminal UI (Rich) – includes Pi Grid mode
requirements.txt
```

---

## Troubleshooting

- **No colors in terminal**: try a different terminal or omit `--mono`. Windows Terminal and PowerShell work well.
- **Slow installs on Pi**: use `PIP_EXTRA_INDEX_URL=https://www.piwheels.org/simple`.
- **Network hiccups**: use `--json` to render previously saved `scores.json` offline.

---

## License

MIT © Christopher Dudley
