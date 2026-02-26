import unittest
from market_health.diversity_constraints import check_diversity, apply_swap


class TestDiversityConstraints(unittest.TestCase):
    def test_hhi_and_max_weight(self):
        w = {"A": 0.50, "B": 0.30, "C": 0.20}
        res = check_diversity(w, max_weight_per_symbol=0.40, min_distinct_symbols=3, hhi_cap=0.34)
        self.assertFalse(res.ok)
        self.assertTrue(any("max_weight_exceeded" in r for r in res.reasons))

    def test_min_distinct(self):
        w = {"A": 0.60, "B": 0.40}
        res = check_diversity(w, max_weight_per_symbol=0.80, min_distinct_symbols=3, hhi_cap=1.0)
        self.assertFalse(res.ok)
        self.assertTrue(any("min_distinct_violated" in r for r in res.reasons))

    def test_apply_swap_moves_weight(self):
        w = {"AAA": 0.60, "BBB": 0.40}
        w2 = apply_swap(w, "AAA", "CCC")  # move all AAA -> CCC
        self.assertAlmostEqual(w2["CCC"], 0.60, places=6)
        self.assertNotIn("AAA", w2)

