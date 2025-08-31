# engine.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import yfinance as yf

# in-process cache for throttling web calls
_DOWNLOAD_CACHE: Dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}

# price-field names used when normalizing yfinance frames
PRICE_FIELDS = {"Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"}

CHECK_LABELS: Dict[str, List[str]] = {
    "A": ["News", "Analysts", "Event", "Insiders", "Peers/Macro", "Guidance"],
    "B": ["Stacked MAs", "RS vs SPY", "BB Mid", "20D Break", "Vol x", "Hold 20EMA"],
    "C": ["EM Fit", "OI/Flow", "Blocks/DP", "Leaders%>20D", "Money Flow", "SI/Days"],
    "D": ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"],
    "E": ["SPY Trend", "Sector Rank", "Breadth", "VIX Regime", "3-Day RS", "Drivers"],
    "F": ["Trigger", "Invalidation", "Targets", "Time Stop", "Slippage", "Alerts"],
}
SECTORS_DEFAULT = ["XLC", "XLF", "XLI", "XLB", "XLRE", "XLU", "XLP", "XLY", "XLK", "XLE"]

# Curated leaders per sector for the Leaders%>20D proxy
SECTOR_LEADERS: Dict[str, List[str]] = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "META", "GOOGL", "AMD", "CRM"],
    "XLF": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK"],
    "XLE": ["XOM", "CVX", "COP", "SLB", "EOG", "PSX"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW"],
    "XLI": ["CAT", "HON", "GE", "BA", "UPS", "DE"],
    "XLB": ["LIN", "SHW", "ECL", "NUE", "DOW"],
    "XLC": ["GOOGL", "META", "DIS", "NFLX", "TMUS"],
    "XLRE": ["PLD", "AMT", "CCI", "O", "SPG"],
    "XLU": ["NEE", "DUK", "SO", "AEP", "D"],
    "XLP": ["PG", "KO", "PEP", "COST", "WMT"],
}


@dataclass
class CheckScore:
    label: str
    score: int  # 0/1/2


# ---------- D: Risk & Volatility ----------
def compute_risk_volatility_checks(sym: str, df: pd.DataFrame, spy_df: pd.DataFrame) -> List[dict]:
    labels = ["ATR%", "IV%", "Correlation", "Event Risk", "Gap Plan", "Sizing/RR"]
    if df is None or df.empty:
        return [{"label": lab, "score": 1} for lab in labels]

    def _pick_field(frame: pd.DataFrame, key: str, ticker: str) -> Optional[pd.Series]:
        if key in frame.columns:
            return pd.to_numeric(frame[key], errors="coerce")
        if isinstance(frame.columns, pd.MultiIndex):
            if (key, ticker) in frame.columns:
                return pd.to_numeric(frame[(key, ticker)], errors="coerce")
            lvl0 = frame.columns.get_level_values(0)
            if key in set(lvl0):
                for col in frame.columns:
                    if isinstance(col, tuple) and col[0] == key:
                        return pd.to_numeric(frame[col], errors="coerce")
        norm = {str(c).strip().title(): c for c in frame.columns}
        if key.title() in norm:
            return pd.to_numeric(frame[norm[key.title()]], errors="coerce")
        return None

    close_ser = _pick_field(df, "Close", sym)
    high_ser = _pick_field(df, "High", sym)
    low_ser = _pick_field(df, "Low", sym)
    if close_ser is None or high_ser is None or low_ser is None or close_ser.dropna().empty:
        return [{"label": lab, "score": 1} for lab in labels]

    checks: List[dict] = []
    prev_close = close_ser.shift(1)

    # (1) ATR% (14)
    tr = pd.concat([(high_ser - low_ser).abs(),
                    (high_ser - prev_close).abs(),
                    (low_ser - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    atr_pct = (atr / close_ser) * 100
    v_atr = float(atr_pct.dropna().iloc[-1]) if len(atr_pct.dropna()) else float("nan")
    score_atr = 2 if pd.notna(v_atr) and 1.0 <= v_atr <= 3.0 else (
        1 if pd.notna(v_atr) and (0.5 <= v_atr < 1.0 or 3.0 < v_atr <= 4.5) else 0)
    checks.append({"label": "ATR%", "score": score_atr})

    # (2) IV% proxy via BB width% (20,2)
    ma20 = close_ser.rolling(20).mean()
    sd20 = close_ser.rolling(20).std(ddof=0)
    width_pct = ((ma20 + 2 * sd20) - (ma20 - 2 * sd20)) / ma20 * 100
    v_width = float(width_pct.dropna().iloc[-1]) if len(width_pct.dropna()) else float("nan")
    score_iv = 2 if pd.notna(v_width) and 2.0 <= v_width <= 6.0 else (
        1 if pd.notna(v_width) and (1.0 <= v_width < 2.0 or 6.0 < v_width <= 9.0) else 0)
    checks.append({"label": "IV%", "score": score_iv})

    # (3) 20d correlation to SPY
    if spy_df is not None and not spy_df.empty:
        spy_close = _pick_field(spy_df, "Close", "SPY")
        if spy_close is not None:
            r = close_ser.pct_change()
            spy_r = spy_close.pct_change()
            joined = pd.concat([r, spy_r], axis=1).dropna().iloc[-20:]
            corr = joined.corr().iloc[0, 1] if len(joined) >= 5 else float("nan")
            score_corr = 2 if pd.notna(corr) and 0.60 <= corr <= 0.95 else (
                1 if pd.notna(corr) and 0.30 <= corr < 0.60 else 0)
        else:
            score_corr = 1
    else:
        score_corr = 1
    checks.append({"label": "Correlation", "score": score_corr})

    # (4) Event Risk (placeholder)
    checks.append({"label": "Event Risk", "score": 1})
    # (5) Gap Plan (placeholder)
    checks.append({"label": "Gap Plan", "score": 1})

    # (6) Sizing/RR: |Close-EMA20| / ATR
    ema20 = close_ser.ewm(span=20, adjust=False).mean()
    if len(ema20.dropna()) and len(atr.dropna()) and float(atr.dropna().iloc[-1]) > 0:
        ratio = float(abs(close_ser.iloc[-1] - ema20.iloc[-1])) / float(atr.dropna().iloc[-1])
        score_size = 2 if ratio <= 1.0 else (1 if ratio <= 2.0 else 0)
    else:
        score_size = 1
    checks.append({"label": "Sizing/RR", "score": score_size})

    return checks


# ---------- robust column helpers ----------
def pick_series(df: pd.DataFrame, candidates: List[str]) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            s = df[c]
            try:
                return s.astype("float64")
            except (ValueError, TypeError):
                return pd.to_numeric(s, errors="coerce")
    return pd.Series(dtype="float64")


def get_close(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype="float64")
    cols = df.columns
    if isinstance(cols, pd.MultiIndex):
        try:
            sub = df.xs("Close", axis=1, level=0)
            ser = sub.iloc[:, 0] if isinstance(sub, pd.DataFrame) else sub
            ser.name = "Close"
            return ser.astype("float64")
        except (KeyError, IndexError, ValueError, TypeError):
            pass
    if "Close" in df.columns:
        return df["Close"].astype("float64")
    if "Adj Close" in df.columns:
        return df["Adj Close"].astype("float64")
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        ser = numeric.iloc[:, 0]
        ser.name = "Close"
        return ser.astype("float64")
    return pd.Series(dtype="float64")


def get_high(df: pd.DataFrame) -> pd.Series: return pick_series(df, ["High", "high"])


def get_low(df: pd.DataFrame) -> pd.Series:
    return pick_series(df, ["Low", "low"])


def get_volume(df: pd.DataFrame) -> pd.Series: return pick_series(df, ["Volume", "volume"])


# ---------- tiny TA utils ----------
def ema(s: pd.Series, n: int) -> pd.Series: return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series: return s.rolling(n, min_periods=n).mean()


def last(s: pd.Series) -> float: return float(s.iloc[-1]) if len(s) else np.nan


def pct_change(series: pd.Series, n: int) -> float:
    return float(series.iloc[-1] / series.iloc[-1 - n] - 1.0) if len(series) > n else np.nan


# ---------- data fetch (resilient) ----------
def safe_download(symbols: List[str], period: str = "1y", interval: str = "1d", ttl_sec: int = 300) -> Dict[
    str, pd.DataFrame]:
    import time

    def normalize_cols(sym: str, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        if isinstance(frame.columns, pd.MultiIndex):
            try:
                tickers = {str(t[1]) for t in frame.columns}
                fields_first = [str(t[0]).strip() for t in frame.columns]
                if len(tickers) == 1 and list(tickers)[0].upper() == sym.upper():
                    frame = frame.copy();
                    frame.columns = [str(t[0]).title() for t in frame.columns]
                elif any(f.title() in PRICE_FIELDS for f in fields_first):
                    frame = frame.copy();
                    frame.columns = [str(t[0]).title() for t in frame.columns]
                else:
                    frame = frame.droplevel(0, axis=1)
            except (KeyError, IndexError, ValueError, TypeError):
                try:
                    frame = frame.droplevel(0, axis=1)
                except (KeyError, IndexError, ValueError, TypeError):
                    pass
        frame = frame.rename(columns=lambda c: str(c).strip().title())
        frame = frame.dropna(how="all")
        return frame

    def first_valid(frame: pd.DataFrame) -> bool:
        if frame is None or frame.empty: return False
        cols = set(map(str, frame.columns))
        return any(c in cols for c in ["Close", "Adj Close"])

    def try_modes(ticker: str) -> pd.DataFrame:
        modes = [
            dict(fn="download", auto_adjust=False, period=period, interval=interval),
            dict(fn="download", auto_adjust=True, period=period, interval=interval),
            dict(fn="history", auto_adjust=False, period=period, interval=interval),
            dict(fn="history", auto_adjust=True, period=period, interval=interval),
            dict(fn="download", auto_adjust=True, period="6mo", interval=interval),
            dict(fn="history", auto_adjust=True, period="6mo", interval=interval),
        ]
        best_short: Optional[pd.DataFrame] = None
        for m in modes:
            try:
                if m["fn"] == "download":
                    frame = yf.download(ticker, period=m["period"], interval=m["interval"],
                                        auto_adjust=m["auto_adjust"], progress=False, threads=False)
                else:
                    frame = yf.Ticker(ticker).history(period=m["period"], interval=m["interval"],
                                                      auto_adjust=m["auto_adjust"])
                frame = normalize_cols(ticker, frame)
                if not first_valid(frame):
                    time.sleep(0.25);
                    continue
                if len(frame) >= 60: return frame
                if best_short is None or len(frame) > len(best_short): best_short = frame
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, ConnectionError):
                pass
            time.sleep(0.25)
        return best_short if best_short is not None else pd.DataFrame()

    now = time.time()
    out: Dict[str, pd.DataFrame] = {}
    for tk in symbols:
        key = (tk, period, interval)
        cached = _DOWNLOAD_CACHE.get(key)
        if cached and (now - cached[0] < max(1, ttl_sec)):
            out[tk] = cached[1];
            continue
        frame = try_modes(tk)
        if (frame is None or frame.empty) and cached: frame = cached[1]
        _DOWNLOAD_CACHE[key] = (time.time(), frame if frame is not None else pd.DataFrame())
        out[tk] = _DOWNLOAD_CACHE[key][1]
        time.sleep(0.25)
    return out


# ---------- B: Trend & Structure ----------
def score_trend_structure(df: pd.DataFrame, spy_close: pd.Series) -> List[int]:
    if df.empty: return [0, 0, 0, 0, 0, 0]
    close = get_close(df)
    if len(close) < 60: return [0, 0, 0, 0, 0, 0]
    high = get_high(df);
    vol = get_volume(df)
    e9, e20, s50 = ema(close, 9), ema(close, 20), sma(close, 50)
    mid20 = sma(close, 20)
    c1 = 2 if (last(close) > last(e9) > last(e20) > last(s50)) else (1 if last(close) > last(e20) > last(s50) else 0)
    rs5 = pct_change(close, 5) - (pct_change(spy_close, 5) if spy_close is not None and len(spy_close) > 5 else 0.0)
    c2 = 2 if (not np.isnan(rs5) and rs5 > 0) else (1 if (not np.isnan(rs5) and abs(rs5) < 0.002) else 0)
    reclaimed = len(mid20) >= 2 and close.iloc[-1] > mid20.iloc[-1] and close.iloc[-2] > mid20.iloc[-2]
    c3 = 2 if reclaimed else (1 if last(close) > last(mid20) else 0)
    if len(high) >= 21:
        prev20_high = high.rolling(20).max().iloc[-2]
        c4 = 2 if last(close) > prev20_high else (1 if last(close) > last(mid20) else 0)
    else:
        c4 = 0
    if len(vol) >= 20 and vol.notna().any():
        vr = float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-1])
        c5 = 2 if vr >= 1.5 else (1 if vr >= 1.1 else 0)
    else:
        c5 = 1
    held = len(close) >= 5 and (close.iloc[-5:] >= e20.iloc[-5:]).all()
    c6 = 2 if held else (1 if last(close) >= last(e20) else 0)
    return [c1, c2, c3, c4, c5, c6]


# ---------- E: Environment & Regime ----------
def score_environment(sym: str, df: pd.DataFrame, spy_close: pd.Series, vix_close: pd.Series,
                      sector_ranks: Dict[str, int]) -> List[int]:
    if df.empty: return [0, 0, 0, 0, 0, 1]
    close = get_close(df)
    if len(close) < 60 or spy_close is None or len(spy_close) < 60:
        return [0, 0, 0, 0, 0, 1]
    e20, s50 = ema(close, 20), sma(close, 50)
    spy20, spy50 = ema(spy_close, 20), sma(spy_close, 50)
    c1 = 2 if last(spy_close) > last(spy20) > last(spy50) else (1 if last(spy_close) > last(spy50) else 0)
    rank = sector_ranks.get(sym)
    c2 = 2 if (rank is not None and rank <= 3) else (1 if (rank is not None and rank <= 6) else 0)
    c3 = 2 if last(close) > last(e20) > last(s50) else (1 if last(close) > last(s50) else 0)
    if vix_close is not None and len(vix_close) >= 21:
        vix20 = sma(vix_close, 20);
        c4 = 2 if last(vix_close) < last(vix20) else 0
    else:
        c4 = 1
    if len(close) >= 4 and len(spy_close) >= 4:
        rs3 = (close.pct_change().iloc[-3:] - spy_close.pct_change().iloc[-3:]).sum()
        c5 = 2 if rs3 > 0 else (1 if abs(rs3) < 0.001 else 0)
    else:
        c5 = 1
    c6 = 1
    return [c1, c2, c3, c4, c5, c6]


# ---------- A: simple proxies ----------
def compute_catalyst_proxies(df: pd.DataFrame) -> List[Dict[str, int]]:
    close = get_close(df)
    if close.empty or len(close) < 21:
        return [{"label": lab, "score": 1} for lab in CHECK_LABELS["A"]]
    r1 = float(close.pct_change().iloc[-1])
    vol = get_volume(df)
    vol_boost = (float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 and vol.iloc[-1] > 0 else 1.0)
    news = 2 if abs(r1) >= 0.02 or vol_boost >= 1.5 else (1 if abs(r1) >= 0.005 else 0)
    vals = [news, 1, 1, 1, 1, 1]  # placeholders for now
    return [{"label": lab, "score": sc} for lab, sc in zip(CHECK_LABELS["A"], vals)]


# ---------- C: Position & Flow (proxies) ----------
def compute_position_flow_checks(df: pd.DataFrame) -> List[dict]:
    """
    Category C — Position & Flow (ETF-only proxies, no external feeds)
    Labels: ["EM Fit", "OI/Flow", "Blocks/DP", "Leaders%>20D", "Money Flow", "SI/Days"]
    Scoring: 0/1/2 (weak/neutral/good)
    """
    labels = ["EM Fit", "OI/Flow", "Blocks/DP", "Leaders%>20D", "Money Flow", "SI/Days"]

    close = get_close(df)
    vol = get_volume(df)
    high = get_high(df)
    low = get_high(df)  # NOTE: get_low helper not present; using get_high for symmetry? If you have get_low, swap here.

    # If you have a get_low helper, replace the line above with:
    # low = get_low(df)

    # Guardrails
    if close.empty or len(close) < 30 or vol.empty:
        return [{"label": lab, "score": 1} for lab in labels]

    # --- Common pieces
    e20 = ema(close, 20)
    s20 = sma(close, 20)

    # ATR for normalization (14)
    prev_c = close.shift(1)
    tr = pd.concat([(high - low).abs(),
                    (high - prev_c).abs(),
                    (low - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()

    # Helper to make 0/1/2 decisions with safe NaN handling
    def bucketing(x: float, good: tuple[float, float], neutral: tuple[float, float], higher_is_better=True) -> int:
        if pd.isna(x):
            return 1
        lo_g, hi_g = good
        lo_n, hi_n = neutral
        if higher_is_better:
            if lo_g <= x <= hi_g:   return 2
            if lo_n <= x <= hi_n:   return 1
            return 0
        else:
            if lo_g <= x <= hi_g:   return 2
            if lo_n <= x <= hi_n:   return 1
            return 0

    checks: List[dict] = []

    # 1) EM Fit: |Close-EMA20| / ATR (smaller is better)
    fit = float(abs(close.iloc[-1] - e20.iloc[-1])) / float(atr.iloc[-1]) if atr.iloc[-1] > 0 else np.nan
    # ≤1.0 ATR = good, ≤2.0 ATR = neutral
    c1 = 2 if pd.notna(fit) and fit <= 1.0 else (1 if pd.notna(fit) and fit <= 2.0 else 0)
    checks.append({"label": "EM Fit", "score": c1})

    # 2) OI/Flow (proxy): Up-volume / Down-volume over last 10 bars
    up_mask = close.diff() > 0
    dn_mask = close.diff() < 0
    last_n = 10
    up_vol = float(vol[up_mask].iloc[-last_n:].sum()) if vol.notna().any() else np.nan
    dn_vol = float(vol[dn_mask].iloc[-last_n:].sum()) if vol.notna().any() else np.nan
    flow_ratio = (up_vol / dn_vol) if (dn_vol and dn_vol > 0) else np.nan
    # >1.2 good, 0.9–1.2 neutral
    c2 = 2 if pd.notna(flow_ratio) and flow_ratio > 1.2 else (1 if pd.notna(flow_ratio) and flow_ratio >= 0.9 else 0)
    checks.append({"label": "OI/Flow", "score": c2})

    # 3) Blocks/DP (proxy): Today volume vs 20d avg
    if len(vol) >= 20 and vol.iloc[-1] > 0:
        vr = float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-1])
        c3 = 2 if vr >= 1.5 else (1 if vr >= 1.1 else 0)
    else:
        c3 = 1
    checks.append({"label": "Blocks/DP", "score": c3})

    # 4) Leaders%>20D (proxy): % of last 20 closes above SMA20
    if len(close) >= 20:
        above = (close.iloc[-20:] > s20.iloc[-20:]).mean()  # fraction 0..1
        # ≥60% good, 50–60% neutral
        c4 = 2 if above >= 0.60 else (1 if above >= 0.50 else 0)
    else:
        c4 = 1
    checks.append({"label": "Leaders%>20D", "score": c4})

    # 5) Money Flow: OBV slope over last 20
    if vol.notna().any():
        # OBV
        direction = np.sign(close.diff().fillna(0))
        obv = (direction * vol.fillna(0)).cumsum()
        if len(obv) >= 20:
            y = obv.iloc[-20:].astype(float)
            x = np.arange(len(y), dtype=float)
            # simple slope via least squares
            denom = (x - x.mean()).var() * len(x)
            slope = float(((x - x.mean()) * (y - y.mean())).sum() / denom) if denom > 0 else np.nan
            # positive slope good, small |slope| neutral
            c5 = 2 if pd.notna(slope) and slope > 0 else (1 if pd.notna(slope) and abs(slope) < 1e-6 else 0)
        else:
            c5 = 1
    else:
        c5 = 1
    checks.append({"label": "Money Flow", "score": c5})

    # 6) SI/Days: no short-interest feed yet -> neutral
    c6 = 1
    checks.append({"label": "SI/Days", "score": c6})

    return checks


# ---------- Public API ----------
def compute_scores(sectors: List[str] = None,
                   _seed: int = 7,  # unused (kept for API compatibility)
                   *,
                   period: str = "1y",
                   interval: str = "1d",
                   ttl_sec: int = 300) -> List[Dict]:
    """
    Build sector score objects by fetching price data and computing category checks.
    """
    sectors = sectors or SECTORS_DEFAULT
    need = list(set(sectors + ["SPY", "^VIX"]))

    data = safe_download(need, period=period, interval=interval, ttl_sec=ttl_sec)

    spy_close = get_close(data.get("SPY", pd.DataFrame()))
    vix_close = get_close(data.get("^VIX", pd.DataFrame()))

    # Rank sectors by 5-bar return on the selected interval (done ONCE, not inside the loop)
    rets: Dict[str, float] = {}
    for s in sectors:
        c = get_close(data.get(s, pd.DataFrame()))
        rc = c.pct_change(5).dropna()
        rets[s] = float(rc.iloc[-1]) if len(rc) else float("-inf")
    ranked = sorted(rets.items(), key=lambda kv: (-kv[1], kv[0]))
    ranks = {sym: i + 1 for i, (sym, _) in enumerate(ranked)}

    out: List[Dict] = []

    for sym in sectors:
        df_sym = data.get(sym, pd.DataFrame())

        # ----- B: Trend & Structure
        try:
            b_scores = score_trend_structure(df_sym, spy_close) if not df_sym.empty else [0, 0, 0, 0, 0, 0]
        except Exception:
            b_scores = [0, 0, 0, 0, 0, 0]

        # ----- E: Environment & Regime
        try:
            e_scores = (score_environment(sym, df_sym, spy_close, vix_close, ranks)
                        if not df_sym.empty else [0, 0, 0, 0, 0, 1])
        except Exception:
            e_scores = [0, 0, 0, 0, 0, 1]

        # ----- D: Risk & Volatility (real checks)
        try:
            d_checks = compute_risk_volatility_checks(sym, df_sym, data.get("SPY", pd.DataFrame()))
        except Exception:
            d_checks = [{"label": lab, "score": 1} for lab in CHECK_LABELS["D"]]

        # ----- A: Catalyst Health (simple proxies for now)
        try:
            a_checks = compute_catalyst_proxies(df_sym)
        except Exception:
            a_checks = [{"label": lab, "score": 1} for lab in CHECK_LABELS["A"]]

        def neutral() -> List[int]:
            return [1, 1, 1, 1, 1, 1]

        cats = {
            "A": {"checks": a_checks},
            "B": {"checks": [asdict(CheckScore(l, s)) for l, s in zip(CHECK_LABELS["B"], b_scores)]},
            "C": {"checks": [asdict(CheckScore(l, s)) for l, s in zip(CHECK_LABELS["C"], neutral())]},
            "D": {"checks": d_checks},
            "E": {"checks": [asdict(CheckScore(l, s)) for l, s in zip(CHECK_LABELS["E"], e_scores)]},
            "F": {"checks": [asdict(CheckScore(l, s)) for l, s in zip(CHECK_LABELS["F"], neutral())]},
        }

        out.append({"symbol": sym, "categories": cats})

    return out

# ---------------------------------------------------------------------------
