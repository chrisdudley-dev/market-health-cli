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

## Scoring framework (A–F categories)

Your framework is organized into **6 categories (A–F)**. Each category contains **6 checks/variables** for a total of **36 distinct factors**. These roll up into each sector’s score and color.

### A — Catalyst Health
**Focus:** external events, sentiment, and “catalysts.”  
**Variables:**
- **News** — recent headlines, sentiment, or price/volume proxy spikes
- **Analysts** — upgrades/downgrades, price targets, recommendations
- **Event** — scheduled catalysts (earnings, product launches, regulatory)
- **Insiders** — insider buying/selling activity
- **Peers/Macro** — sector‑wide or macro catalysts impacting the symbol
- **Guidance** — outlook revisions and earnings guidance

### B — Trend & Structure
**Focus:** technical price/volume structure.  
**Variables:**
- **Stacked MAs** — alignment 9EMA > 20EMA > 50SMA
- **RS vs SPY** — 5‑day relative strength versus SPY
- **BB Mid** — reclaim of the 20‑day SMA (Bollinger mid)
- **20D Break** — breakout above the 20‑day high
- **Vol ×** — volume expansion vs. 20‑day average
- **Hold 20EMA** — pullbacks respecting the 20EMA

### C — Position & Flow
**Focus:** positioning, flows, participation.  
**Variables:**
- **EM Fit** — fit to an exponential moving structure
- **OI/Flow** — options open interest & flow activity
- **Blocks/DP** — large prints / dark‑pool activity
- **Leaders% > 20D** — % of leaders above 20‑day MA
- **Money Flow** — net inflows/outflows
- **SI/Days** — short interest vs. average daily volume

### D — Risk & Volatility
**Focus:** volatility, correlation, risk control.  
**Variables:**
- **ATR%** — Average True Range as % of price
- **IV%** — implied volatility proxy (e.g., BB width)
- **Correlation** — 20‑day correlation vs. SPY
- **Event Risk** — earnings/event risk placeholder
- **Gap Plan** — gap‑risk strategy placeholder
- **Sizing/RR** — position sizing & risk/reward vs ATR/EMA

### E — Environment & Regime
**Focus:** broader market/sector regime.  
**Variables:**
- **SPY Trend** — SPY alignment with 20/50‑day averages
- **Sector Rank** — relative rank of sector ETF (e.g., 5‑bar return)
- **Breadth** — sector breadth / internal trend health
- **VIX Regime** — VIX vs. its 20‑day SMA (calm vs stressed)
- **3‑Day RS** — short‑term RS vs. SPY
- **Drivers** — macro drivers alignment (placeholder)

### F — Execution & Frictions
**Focus:** trade management and execution discipline.  
**Variables:**
- **Trigger** — defined trade trigger present
- **Invalidation** — clear stop/invalid level
- **Targets** — realistic upside targets
- **Time Stop** — time‑based exit rule
- **Slippage** — liquidity / bid‑ask cost
- **Alerts** — monitoring/alerting in place

> **Summary:** 36 checks total (6 × 6). A–C emphasize catalysts/technicals/positioning; D–E cover risk and environment; F captures execution discipline.

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
    "B": [{"label": "...", "score": 0}],
    "C": [{"label": "...", "score": 2}],
    "D": [{"label": "...", "score": 1}],
    "E": [{"label": "...", "score": 1}],
    "F": [{"label": "...", "score": 0}]
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
