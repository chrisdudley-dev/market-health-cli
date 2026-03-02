import datetime as dt
import pytest

from market_health.trading_days import (
    add_trading_days,
    is_trading_day,
    next_trading_day,
)


def d(y, m, day):
    return dt.date(y, m, day)


@pytest.mark.parametrize(
    "inp, n, expected",
    [
        (d(2026, 2, 23), 0, d(2026, 2, 23)),  # Mon
        (d(2026, 2, 23), 1, d(2026, 2, 24)),  # Mon+1
        (d(2026, 2, 27), 1, d(2026, 3, 2)),  # Fri+1 => Mon
        (d(2026, 2, 27), 5, d(2026, 3, 6)),  # Fri+5 => next Fri
        (d(2026, 2, 28), 0, d(2026, 3, 2)),  # Sat roll => Mon
        (d(2026, 2, 28), 1, d(2026, 3, 3)),  # Sat roll Mon, +1 => Tue
        (d(2026, 3, 1), 0, d(2026, 3, 2)),  # Sun roll => Mon
    ],
)
def test_add_trading_days_weekends_only(inp, n, expected):
    assert add_trading_days(inp, n) == expected


def test_next_trading_day_rolls_forward():
    assert next_trading_day(d(2026, 2, 28)) == d(2026, 3, 2)  # Sat -> Mon
    assert next_trading_day(d(2026, 3, 1)) == d(2026, 3, 2)  # Sun -> Mon


def test_is_trading_day():
    assert is_trading_day(d(2026, 2, 23))
    assert not is_trading_day(d(2026, 2, 28))


def test_negative_rejected():
    with pytest.raises(ValueError):
        add_trading_days(d(2026, 2, 23), -1)
