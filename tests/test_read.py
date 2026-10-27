import time

import pandas as pd
import pytest

from tabsight.read import read_dates, read_numbers, sample, unit_from_name


def s(values: list[object]) -> pd.Series:
    return pd.Series(values, dtype=object)


def test_iso_dates() -> None:
    r = read_dates(s(["2017-01-05", "2017-02-06", None]))
    assert r is not None and not r.assumed and r.dayfirst is None
    assert r.values.iloc[0] == pd.Timestamp("2017-01-05")
    assert pd.isna(r.values.iloc[2])


def test_day_first_proven_by_data() -> None:
    r = read_dates(s(["16/06/2016", "01/02/2016", "11-08-2016"]))
    assert r is not None and r.dayfirst is True and not r.assumed
    assert r.values.iloc[1] == pd.Timestamp("2016-02-01")
    assert r.values.iloc[2] == pd.Timestamp("2016-08-11")  # mixed separators normalised


def test_month_first_proven_by_data() -> None:
    r = read_dates(s(["6/16/2016", "11-08-2016", "1/2/2016"]))
    assert r is not None and r.dayfirst is False and not r.assumed
    assert r.values.iloc[1] == pd.Timestamp("2016-11-08")


def test_ambiguous_order_is_assumed_and_reported() -> None:
    r = read_dates(s(["01/02/2016", "03/04/2016"]), dayfirst=True)
    assert r is not None and r.assumed and r.dayfirst is True
    assert r.values.iloc[0] == pd.Timestamp("2016-02-01")
    r2 = read_dates(s(["01/02/2016", "03/04/2016"]))
    assert r2 is not None and r2.assumed and r2.dayfirst is False


def test_contradictory_values_are_not_dates() -> None:
    assert read_dates(s(["13/01/2016", "01/13/2016"])) is None


def test_times_and_text_months() -> None:
    r = read_dates(s(["2017-01-05 13:45", "2017-01-06 08:00:30"]))
    assert r is not None and r.values.iloc[0] == pd.Timestamp("2017-01-05 13:45")
    m = read_dates(s(["Jan 2017", "Feb 2017", "Mar 2017"]))
    assert m is not None and m.values.iloc[2] == pd.Timestamp("2017-03-01")


def test_zero_threshold_still_picks_the_right_layout() -> None:
    """Regression: threshold=0 used to make every structural check pass (read as year-first)."""
    r = read_dates(s(["01/15/2017", "03/02/2017", "junk"]), threshold=0.0)
    assert r is not None and r.format == "%m/%d/%Y"
    assert r.values.iloc[0] == pd.Timestamp("2017-01-15") and pd.isna(r.values.iloc[2])
    m = read_dates(s(["5 Jan 2017", "Feb 2017"]), threshold=0.0)
    assert m is not None and m.values.notna().sum() == 1


def test_non_dates() -> None:
    assert read_dates(s(["West", "East"])) is None
    assert read_dates(pd.Series([1, 2, 3])) is None
    assert read_dates(s(["2017-01-05"] * 50 + ["junk"] * 10)) is None  # below 95%


@pytest.mark.parametrize(
    ("values", "expected", "unit", "symbol"),
    [
        (["$1,234.50", "$10", "($500.00)"], [1234.5, 10.0, -500.0], "currency", "$"),
        (["15%", "7.5%", "-2%"], [15.0, 7.5, -2.0], "percent", None),
        (["1.234,5 €", "10,25 €", "3 €"], [1234.5, 10.25, 3.0], "currency", "€"),
        (["£1,000", "£2,500.75"], [1000.0, 2500.75], "currency", "£"),
        (["1,234.5", "2,000"], [1234.5, 2000.0], "number", None),
    ],
)
def test_numbers_as_text(
    values: list[str], expected: list[float], unit: str, symbol: str | None
) -> None:
    r = read_numbers(s(values))
    assert r is not None
    assert r.values.tolist() == expected
    assert r.unit == unit and r.currency_symbol == symbol


def test_plain_integer_text_is_left_alone() -> None:
    assert read_numbers(s(["02134", "10001"])) is None
    assert read_numbers(s(["West", "East"])) is None


def test_unit_from_name() -> None:
    assert unit_from_name("Sales (€)") == ("currency", "EUR")
    assert unit_from_name("Price_USD") == ("currency", "USD")
    assert unit_from_name("Duration_hrs") == ("duration", "hours")
    assert unit_from_name("Growth (%)") == ("percent", None)
    assert unit_from_name("Sales") is None


def test_sample_is_deterministic() -> None:
    big = pd.Series(range(50_000))
    a, b = sample(big), sample(big)
    assert len(a) == 10_000 and a.equals(b)


def test_hostile_long_strings_are_fast() -> None:
    """No catastrophic regex backtracking on adversarial input."""
    evil = s(["1" * 100_000 + "x", " " * 50_000 + "1", "1/" * 20_000, "(" * 10_000])
    start = time.perf_counter()
    assert read_dates(evil) is None
    assert read_numbers(evil) is None
    assert unit_from_name("_" * 100_000 + "x") is None
    assert time.perf_counter() - start < 2.0
