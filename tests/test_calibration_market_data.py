from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from market_health.calibration.market_data import (
    build_market_data_diagnostics,
    market_data_diagnostics_path,
    write_market_data_diagnostics,
)
from market_health.calibration.price_cache import HistoricalPriceRow
from market_health.calibration.runner import run_fixture_market_data_replay
from market_health.calibration.warmup_window import (
    resolve_replay_warmup_window,
)


class MarketDataDiagnosticsTest(unittest.TestCase):
    def test_diagnostics_report_missing_and_partial_data(self) -> None:
        window = resolve_replay_warmup_window(
            [
                _row("SPY", date(2026, 5, 21), 101.0),
                _row("SPY", date(2026, 5, 22), 102.0),
                _row("QQQ", date(2026, 5, 21), 201.0),
                _row("IWM", date(2026, 5, 23), 51.0),
            ],
            replay_date=date(2026, 5, 22),
            lookback_rows=2,
            symbols=["SPY", "QQQ", "IWM"],
        )

        diagnostics = build_market_data_diagnostics(window)

        self.assertEqual(diagnostics.available_symbols, ("QQQ", "SPY"))
        self.assertEqual(diagnostics.missing_symbols, ("IWM",))
        self.assertEqual(
            diagnostics.missing_replay_date_symbols,
            ("QQQ", "IWM"),
        )
        self.assertEqual(diagnostics.partial_warmup_symbols, ("QQQ",))
        self.assertEqual(
            [
                (
                    item.symbol,
                    item.available_rows,
                    item.has_replay_date_row,
                    item.is_missing_symbol,
                    item.is_partial_warmup,
                )
                for item in diagnostics.symbols
            ],
            [
                ("SPY", 2, True, False, False),
                ("QQQ", 1, False, False, True),
                ("IWM", 0, False, True, False),
            ],
        )

    def test_diagnostics_writer_outputs_stable_json(self) -> None:
        window = resolve_replay_warmup_window(
            [_row("SPY", date(2026, 5, 22), 102.0)],
            replay_date=date(2026, 5, 22),
            lookback_rows=1,
            symbols=["SPY"],
        )
        diagnostics = build_market_data_diagnostics(window)

        with tempfile.TemporaryDirectory() as tmp:
            path = market_data_diagnostics_path(
                Path(tmp),
                date(2026, 5, 22),
            )
            write_market_data_diagnostics(path, diagnostics)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload["schema_version"],
            "calibration_market_data_diagnostics.v1",
        )
        self.assertEqual(payload["replay_date"], "2026-05-22")
        self.assertEqual(payload["missing_symbols"], [])

    def test_runner_uses_fixture_market_data_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "calibration"
            result = run_fixture_market_data_replay(
                output_root=output_root,
                replay_dates=[date(2026, 5, 22)],
                symbols=["SPY", "QQQ", "IWM"],
                price_rows=[
                    _row("SPY", date(2026, 5, 21), 101.0),
                    _row("SPY", date(2026, 5, 22), 102.0),
                    _row("QQQ", date(2026, 5, 21), 201.0),
                    _row("IWM", date(2026, 5, 23), 51.0),
                ],
                lookback_rows=2,
            )

            with result.csv_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))

            diagnostics_payload = json.loads(
                market_data_diagnostics_path(
                    output_root,
                    date(2026, 5, 22),
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(len(csv_rows), 1)
        self.assertEqual([row["symbol"] for row in csv_rows], ["SPY"])
        self.assertEqual(
            diagnostics_payload["missing_replay_date_symbols"],
            ["QQQ", "IWM"],
        )
        self.assertEqual(diagnostics_payload["partial_warmup_symbols"], ["QQQ"])


def _row(symbol: str, price_date: date, close: float) -> HistoricalPriceRow:
    return HistoricalPriceRow(
        symbol=symbol,
        date=price_date,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        adjusted_close=close,
        volume=1000,
    )


if __name__ == "__main__":
    unittest.main()
