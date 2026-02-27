import unittest
from datetime import datetime, timedelta, date

from market_health.cooldown_policy import SwapEvent, check_cooldown


class TestCooldownPolicy(unittest.TestCase):
    def test_veto_same_pair_either_direction(self):
        now = datetime(2026, 2, 26, 12, 0, 0)
        hist = [
            SwapEvent(ts=now - timedelta(days=2), from_symbol="XLK", to_symbol="XLF"),
        ]
        res = check_cooldown(
            proposed_from="XLF",
            proposed_to="XLK",
            history=hist,
            cooldown_trading_days=5,
            now_trade_date=date(2026, 2, 26),
        )
        self.assertTrue(res.vetoed)
        self.assertIn("cooldown", res.veto_reason)

    def test_no_veto_after_window(self):
        now = datetime(2026, 2, 26, 12, 0, 0)
        hist = [
            SwapEvent(ts=now - timedelta(days=10), from_symbol="XLK", to_symbol="XLF")
        ]
        res = check_cooldown(
            proposed_from="XLK",
            proposed_to="XLF",
            history=hist,
            cooldown_trading_days=5,
            now_trade_date=date(2026, 2, 26),
        )
        self.assertFalse(res.vetoed)

    def test_disable_when_zero(self):
        now = datetime(2026, 2, 26, 12, 0, 0)
        hist = [
            SwapEvent(ts=now - timedelta(days=1), from_symbol="XLK", to_symbol="XLF")
        ]
        res = check_cooldown(
            proposed_from="XLK",
            proposed_to="XLF",
            history=hist,
            cooldown_trading_days=0,
        )
        self.assertFalse(res.vetoed)


if __name__ == "__main__":
    unittest.main()
