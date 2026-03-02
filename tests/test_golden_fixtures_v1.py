import json
import unittest
from pathlib import Path

from market_health.golden_fixtures_v1 import generate_golden_fixtures_v1


class TestGoldenFixturesV1(unittest.TestCase):
    def test_golden_forecast_and_recommendation(self) -> None:
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        forecast_p = fixtures_dir / "golden.forecast_scores.v1.json"
        rec_p = fixtures_dir / "golden.recommendation.forecast.v1.json"

        self.assertTrue(
            forecast_p.exists(),
            msg="Missing forecast fixture; run scripts/dev/update_golden_fixtures_v1.py",
        )
        self.assertTrue(
            rec_p.exists(),
            msg="Missing recommendation fixture; run scripts/dev/update_golden_fixtures_v1.py",
        )

        want_forecast = json.loads(forecast_p.read_text(encoding="utf-8"))
        want_rec = json.loads(rec_p.read_text(encoding="utf-8"))

        got = generate_golden_fixtures_v1()

        self.assertEqual(
            want_forecast,
            got["forecast"],
            msg="Forecast fixture mismatch. Run scripts/dev/update_golden_fixtures_v1.py to refresh.",
        )
        self.assertEqual(
            want_rec,
            got["recommendation"],
            msg="Recommendation fixture mismatch. Run scripts/dev/update_golden_fixtures_v1.py to refresh.",
        )


if __name__ == "__main__":
    unittest.main()
