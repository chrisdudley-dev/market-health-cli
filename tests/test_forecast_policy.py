import unittest
from market_health.forecast_policy import compute_multi_horizon_edge


class TestForecastPolicy(unittest.TestCase):
    def test_robust_edge_is_min(self):
        scores = {
            "AAA": {1: {"forecast_score": 0.50}, 5: {"forecast_score": 0.55}},
            "BBB": {1: {"forecast_score": 0.60}, 5: {"forecast_score": 0.56}},
        }
        mh = compute_multi_horizon_edge(from_symbol="AAA", to_symbol="BBB", scores=scores, horizons_trading_days=(1, 5))
        self.assertAlmostEqual(mh.edges_by_h[1], 0.10, places=6)
        self.assertAlmostEqual(mh.edges_by_h[5], 0.01, places=6)
        self.assertAlmostEqual(mh.robust_edge, 0.01, places=6)
        self.assertFalse(mh.vetoed)

    def test_disagreement_veto(self):
        scores = {
            "AAA": {1: {"forecast_score": 0.50}, 5: {"forecast_score": 0.55}},
            "BBB": {1: {"forecast_score": 0.60}, 5: {"forecast_score": 0.40}},
        }
        mh = compute_multi_horizon_edge(
            from_symbol="AAA",
            to_symbol="BBB",
            scores=scores,
            horizons_trading_days=(1, 5),
            disagreement_veto_edge=0.0,
        )
        self.assertTrue(mh.vetoed)
        self.assertIn("disagreement_veto", mh.veto_reason)

    def test_missing_horizon_veto(self):
        scores = {
            "AAA": {1: {"forecast_score": 0.50}},
            "BBB": {1: {"forecast_score": 0.60}, 5: {"forecast_score": 0.61}},
        }
        mh = compute_multi_horizon_edge(from_symbol="AAA", to_symbol="BBB", scores=scores, horizons_trading_days=(1, 5))
        self.assertTrue(mh.vetoed)
        self.assertIn("missing_horizons:5", mh.veto_reason)


if __name__ == "__main__":
    unittest.main()
