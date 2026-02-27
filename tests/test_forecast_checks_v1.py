import unittest
from typing import Any, Dict

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe


def _ohlcv_trend(n: int = 80, direction: int = 1) -> OHLCV:
    """direction=+1 => gentle uptrend, direction=-1 => gentle downtrend."""
    base = 100.0
    close = [base + direction * (i * 0.25) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    vol = [1_000_000.0 for _ in close]
    return OHLCV(close=close, high=high, low=low, volume=vol)


def _ohlcv_close_only(n: int = 60) -> OHLCV:
    close = [100.0 + (i * 0.1) for i in range(n)]
    return OHLCV(close=close, high=None, low=None, volume=None)


def _assert_payload_contract(tc: unittest.TestCase, payload: Dict[str, Any]) -> None:
    tc.assertIn("forecast_score", payload)
    tc.assertIsInstance(payload["forecast_score"], (int, float))
    tc.assertGreaterEqual(float(payload["forecast_score"]), 0.0)
    tc.assertLessEqual(float(payload["forecast_score"]), 1.0)

    tc.assertIn("points", payload)
    tc.assertIn("max_points", payload)
    tc.assertIsInstance(payload["points"], int)
    tc.assertIsInstance(payload["max_points"], int)
    tc.assertGreater(payload["max_points"], 0)

    cats = payload.get("categories")
    tc.assertIsInstance(cats, dict)

    # A–E × 6 checks each (30 total)
    for k in ("A", "B", "C", "D", "E"):
        tc.assertIn(k, cats)
        cat = cats[k]
        tc.assertIsInstance(cat, dict)

        checks = cat.get("checks")
        tc.assertIsInstance(checks, list)
        tc.assertEqual(
            len(checks),
            6,
            msg=f"Category {k} must have exactly 6 checks (got {len(checks)})",
        )

        for chk in checks:
            tc.assertIsInstance(chk, dict)
            tc.assertIsInstance(chk.get("label"), str)
            tc.assertIsInstance(chk.get("meaning"), str)
            tc.assertIn(chk.get("score"), (0, 1, 2))
            tc.assertIsInstance(chk.get("metrics"), dict)


class TestForecastChecksV1(unittest.TestCase):
    def test_contract_shape_h1_h5(self) -> None:
        universe = {
            "SPY": _ohlcv_trend(),
            "XLK": _ohlcv_trend(),
            "XLF": _ohlcv_trend(),
        }

        scores = compute_forecast_universe(
            universe=universe,
            spy=universe["SPY"],
            horizons_trading_days=(1, 5),
        )
        self.assertIsInstance(scores, dict)
        self.assertIn("SPY", scores)

        by_h = scores["SPY"]
        self.assertIsInstance(by_h, dict)
        self.assertIn(1, by_h)
        self.assertIn(5, by_h)

        _assert_payload_contract(self, by_h[1])
        _assert_payload_contract(self, by_h[5])

    def test_missing_data_close_only_does_not_crash(self) -> None:
        universe = {
            "SPY": _ohlcv_close_only(),
            "XLK": _ohlcv_close_only(),
            "XLF": _ohlcv_close_only(),
        }
        scores = compute_forecast_universe(
            universe=universe,
            spy=universe["SPY"],
            horizons_trading_days=(1, 5),
        )
        self.assertIn("SPY", scores)
        _assert_payload_contract(self, scores["SPY"][1])
        _assert_payload_contract(self, scores["SPY"][5])

    def test_too_short_series_is_fail_soft(self) -> None:
        short = OHLCV(close=[100.0, 101.0, 102.0], high=None, low=None, volume=None)
        universe = {"SPY": short, "XLK": short, "XLF": short}
        scores = compute_forecast_universe(
            universe=universe,
            spy=universe["SPY"],
            horizons_trading_days=(1, 5),
        )
        self.assertIn("SPY", scores)
        _assert_payload_contract(self, scores["SPY"][1])
        _assert_payload_contract(self, scores["SPY"][5])

    def test_boundary_uptrend_vs_downtrend_changes_score(self) -> None:
        up = {
            "SPY": _ohlcv_trend(direction=1),
            "XLK": _ohlcv_trend(direction=1),
            "XLF": _ohlcv_trend(direction=1),
        }
        dn = {
            "SPY": _ohlcv_trend(direction=-1),
            "XLK": _ohlcv_trend(direction=-1),
            "XLF": _ohlcv_trend(direction=-1),
        }

        scores_up = compute_forecast_universe(
            universe=up, spy=up["SPY"], horizons_trading_days=(5,)
        )
        scores_dn = compute_forecast_universe(
            universe=dn, spy=dn["SPY"], horizons_trading_days=(5,)
        )

        s_up = float(scores_up["SPY"][5]["forecast_score"])
        s_dn = float(scores_dn["SPY"][5]["forecast_score"])

        # We don't pin exact values (too brittle), but direction should matter.
        self.assertNotAlmostEqual(s_up, s_dn, places=6)


if __name__ == "__main__":
    unittest.main()
