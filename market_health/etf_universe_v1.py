from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_ETFS: list[dict[str, Any]] = [
    {
        "symbol": "IBIT",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "BITI",
        "enabled": True,
        "inverse_or_levered": True,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "SBIT",
        "enabled": True,
        "inverse_or_levered": True,
        "strategy_wrapper": False,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "BTCI",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "QYLD",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "equity_income",
    },
    {
        "symbol": "JEPI",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "equity_income",
    },
    {
        "symbol": "BLOK",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "blockchain",
    },
    {
        "symbol": "BITC",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": True,
        "overlap_key": "bitcoin",
    },
    {
        "symbol": "ETHA",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "ethereum",
    },
    {
        "symbol": "BKCH",
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": "blockchain",
    },
]


GLOBAL_BROAD_MARKET_ETF_ROWS: list[tuple[str, str, str, str]] = [
    # symbol, country, region, overlap_key
    ("EWC", "Canada", "Americas", "country_canada"),
    ("EWW", "Mexico", "Americas", "country_mexico"),
    ("EWZ", "Brazil", "Americas", "country_brazil"),
    ("ECH", "Chile", "Americas", "country_chile"),
    ("EPU", "Peru", "Americas", "country_peru"),
    ("ARGT", "Argentina", "Americas", "country_argentina"),
    ("EWU", "United Kingdom", "Europe", "country_united_kingdom"),
    ("EWG", "Germany", "Europe", "country_germany"),
    ("EWQ", "France", "Europe", "country_france"),
    ("EWI", "Italy", "Europe", "country_italy"),
    ("EWP", "Spain", "Europe", "country_spain"),
    ("EWL", "Switzerland", "Europe", "country_switzerland"),
    ("EWN", "Netherlands", "Europe", "country_netherlands"),
    ("EWD", "Sweden", "Europe", "country_sweden"),
    ("EDEN", "Denmark", "Europe", "country_denmark"),
    ("EFNL", "Finland", "Europe", "country_finland"),
    ("EIRL", "Ireland", "Europe", "country_ireland"),
    ("EWO", "Austria", "Europe", "country_austria"),
    ("EWK", "Belgium", "Europe", "country_belgium"),
    ("ENOR", "Norway", "Europe", "country_norway"),
    ("EPOL", "Poland", "Europe", "country_poland"),
    ("TUR", "Turkey", "Europe", "country_turkey"),
    ("GREK", "Greece", "Europe", "country_greece"),
    ("EWA", "Australia", "Asia-Pacific", "country_australia"),
    ("EWH", "Hong Kong", "Asia-Pacific", "country_hong_kong"),
    ("INDA", "India", "Asia-Pacific", "country_india"),
    ("MCHI", "China", "Asia-Pacific", "country_china"),
    ("EWY", "South Korea", "Asia-Pacific", "country_south_korea"),
    ("EWT", "Taiwan", "Asia-Pacific", "country_taiwan"),
    ("EWS", "Singapore", "Asia-Pacific", "country_singapore"),
    ("EWM", "Malaysia", "Asia-Pacific", "country_malaysia"),
    ("EIDO", "Indonesia", "Asia-Pacific", "country_indonesia"),
    ("THD", "Thailand", "Asia-Pacific", "country_thailand"),
    ("EPHE", "Philippines", "Asia-Pacific", "country_philippines"),
    ("ENZL", "New Zealand", "Asia-Pacific", "country_new_zealand"),
    ("VNAM", "Vietnam", "Asia-Pacific", "country_vietnam"),
    ("EIS", "Israel", "Middle East / Africa", "country_israel"),
    ("KSA", "Saudi Arabia", "Middle East / Africa", "country_saudi_arabia"),
    ("QAT", "Qatar", "Middle East / Africa", "country_qatar"),
    (
        "UAE",
        "United Arab Emirates",
        "Middle East / Africa",
        "country_united_arab_emirates",
    ),
    ("EZA", "South Africa", "Middle East / Africa", "country_south_africa"),
]


GLOBAL_BROAD_MARKET_ETFS: list[dict[str, Any]] = [
    {
        "symbol": symbol,
        "enabled": True,
        "inverse_or_levered": False,
        "strategy_wrapper": False,
        "overlap_key": overlap_key,
        "family": "global_broad_market",
        "country": country,
        "region": region,
        "exposure": "single_country_broad_equity",
    }
    for symbol, country, region, overlap_key in GLOBAL_BROAD_MARKET_ETF_ROWS
]

DEFAULT_ETFS.extend(GLOBAL_BROAD_MARKET_ETFS)

ENV_VAR = "JERBOA_ETF_UNIVERSE_JSON"


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_etf_universe(
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Load ETF config.

    Only reads from disk if:
      - `path` is provided, OR
      - env var JERBOA_ETF_UNIVERSE_JSON is set.

    Otherwise returns DEFAULT_ETFS (deterministic for tests/CI).
    """
    p: Path | None = None
    if path:
        p = Path(path).expanduser()
    else:
        env = os.environ.get(ENV_VAR)
        if env:
            p = Path(env).expanduser()

    if p and p.exists():
        doc = _read_json(p)
        if isinstance(doc, dict) and isinstance(doc.get("symbols"), list):
            return [x for x in doc["symbols"] if isinstance(x, dict)]
        if isinstance(doc, list):
            return [x for x in doc if isinstance(x, dict)]

    return list(DEFAULT_ETFS)
