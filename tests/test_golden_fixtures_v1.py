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

        if want_forecast != got["forecast"]:
            import hashlib

            def _h(x):
                return hashlib.sha256(
                    json.dumps(x, sort_keys=True).encode()
                ).hexdigest()

            def _first_diff(a, b, path="root"):
                if type(a) is not type(b):
                    return path, a, b

                if isinstance(a, dict):
                    for k in sorted(set(a) | set(b)):
                        if k not in a:
                            return f"{path}.{k}", "<missing>", b[k]
                        if k not in b:
                            return f"{path}.{k}", a[k], "<missing>"
                        diff = _first_diff(a[k], b[k], f"{path}.{k}")
                        if diff is not None:
                            return diff
                    return None

                if isinstance(a, list):
                    if len(a) != len(b):
                        return f"{path}.length", len(a), len(b)
                    for i, (xa, xb) in enumerate(zip(a, b)):
                        diff = _first_diff(xa, xb, f"{path}[{i}]")
                        if diff is not None:
                            return diff
                    return None

                if a != b:
                    return path, a, b

                return None

            print("FORECAST WANT HASH:", _h(want_forecast))
            print("FORECAST GOT  HASH:", _h(got["forecast"]))

            diff = _first_diff(want_forecast, got["forecast"])
            if diff is not None:
                path, a, b = diff
                print("FIRST DIFF PATH:", path)
                print("WANT VALUE:", json.dumps(a, sort_keys=True, default=str))
                print("GOT  VALUE:", json.dumps(b, sort_keys=True, default=str))

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
