import unittest
from typing import Dict, Any

from market_health.forecast_features import OHLCV
from market_health.forecast_score_provider import compute_forecast_universe


def _ohlcv_trend(n: int = 80, direction: int = 1) -> OHLCV:
    """
    direction=+1 => gentle uptrend
    direction=-1 => gentle downtrend
    """
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
    def test_contract_shape_h1_h5(self):
        universe = {
            "SPY": _ohlcv_trend(),
            "XLK": _ohlcv_trend(),
            "XLF": _ohlcv_trend(),
        }
        doc = compute_forecast_universe(universe, horizons_trading_days=(1, 5))
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc.get("schema"), "forecast_scores.v1")

        scores = doc.get("scores")
        self.assertIsInstance(scores, dict)
        self.assertIn("SPY", scores)

        by_h = scores["SPY"]
        self.assertIsInstance(by_h, dict)
        self.assertIn(1, by_h)  # may be int keys
        self.assertIn(5, by_h)

        _assert_payload_contract(self, by_h[1])
        _assert_payload_contract(self, by_h[5])

    def test_missing_data_close_only_does_not_crash(self):
        # close-only should be valid input and should yield a valid payload contract
        universe = {
            "SPY": _ohlcv_close_only(),
            "XLK": _ohlcv_close_only(),
            "XLF": _ohlcv_close_only(),
        }
        doc = compute_forecast_universe(universe, horizons_trading_days=(1, 5))
        self.assertEqual(doc.get("schema"), "forecast_scores.v1")
        scores = doc["scores"]
        _assert_payload_contract(self, scores["SPY"][1])
        _assert_payload_contract(self, scores["SPY"][5])

    def test_too_short_series_is_fail_soft(self):
        # Short series should not raise; it should still return a contract-valid payload
        short = _ohlcv_trend(n=10, direction=1)
        doc = compute_forecast_universe(
            {"SPY": short, "XLK": short, "XLF": short}, horizons_trading_days=(1, 5)
        )
        self.assertEqual(doc.get("schema"), "forecast_scores.v1")
        scores = doc["scores"]
        _assert_payload_contract(self, scores["SPY"][1])

    def test_boundary_uptrend_vs_downtrend_changes_score(self):
        up = {"SPY": _ohlcv_trend(direction=1), "XLK": _ohlcv_trend(direction=1)}
        dn = {"SPY": _ohlcv_trend(direction=-1), "XLK": _ohlcv_trend(direction=-1)}

        doc_up = compute_forecast_universe(up, horizons_trading_days=(5,))
        doc_dn = compute_forecast_universe(dn, horizons_trading_days=(5,))

        s_up = float(doc_up["scores"]["SPY"][5]["forecast_score"])
        s_dn = float(doc_dn["scores"]["SPY"][5]["forecast_score"])

        # Not asserting which direction is "better"—just that the model responds to a strong regime change.
        self.assertNotEqual(
            s_up,
            s_dn,
            msg="Uptrend vs downtrend should change forecast_score in at least one horizon.",
        )


if __name__ == "__main__":
    unittest.main()
