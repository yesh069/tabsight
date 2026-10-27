import math

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tabsight.settings as cfg
from tabsight.formats import NBSP, NNBSP, choose_decimals, format_date, format_number, parse_pattern
from tabsight.i18n import month_name, text
from tabsight.warnings import FormatWarning, InvalidSpecError

fn = format_number


@pytest.mark.parametrize(
    ("value", "unit", "style", "expected"),
    [
        (2297200.8574, "currency", "compact", "$2.3M"),
        (2297200.8574, "currency", "full", "$2,297,201"),
        (35.5, "currency", "full", "$35.50"),
        (-1234.4, "currency", "full", "-$1,234"),
        (999_950, "currency", "compact", "$1M"),  # promoted after rounding, not $1000K
        (50_000, "number", "compact", "50K"),
        (0.156, "percent", "full", "15.6%"),
        (0.15, "percent", "full", "15%"),
        (5009, "count", "full", "5,009"),
        (12.3456, "number", "full", "12.35"),
        (2.5, "count", "full", "3"),  # half-up, not banker's rounding
        (0.0, "currency", "compact", "$0"),
        (2297200.8574, "number", "raw", "2297200.8574"),
    ],
)
def test_english_formats(value: float, unit: str, style: str, expected: str) -> None:
    assert fn(value, unit, style) == expected


def test_missing_values_are_blank() -> None:
    for v in (None, math.nan, math.inf, -math.inf, pd.NA, pd.NaT):
        assert fn(v, "currency") == ""


def test_values_that_overflow_while_scaling_are_blank() -> None:
    # Found by the fuzz test on Python 3.11: 1.797e306 * 100 overflows to infinity.
    assert fn(1.797693134862316e306, "percent", "compact") == ""
    assert fn(1e305, "duration", duration_unit="days") == ""


def test_negative_options_and_signs() -> None:
    assert fn(-1234, "currency", negative="parens") == "($1,234)"
    assert fn(0.082, "percent", sign=True) == "+8.2%"
    assert fn(0.032, "pp") == "+3.2 pp"
    assert fn(-0.0001, "currency", decimals=2) == "$0.00"  # no "-0"


def test_locales() -> None:
    assert fn(1234.5, "currency", locale="en_IE", currency="EUR", decimals=2) == "€1,234.50"
    assert fn(1234.5, "currency", locale="de_DE", currency="EUR", decimals=2) == f"1.234,50{NBSP}€"
    assert fn(0.156, "percent", locale="de_DE") == f"15,6{NBSP}%"
    assert (
        fn(2_300_000, "currency", "compact", locale="de_DE", currency="EUR")
        == f"2,3{NBSP}Mio.{NBSP}€"
    )
    assert fn(123456, "number", locale="en_IN") == "1,23,456"
    assert fn(12_345_678, "number", locale="en_IN") == "1,23,45,678"
    assert fn(1_230_000, "currency", "compact", locale="en_IN", currency="INR") == "₹12.3L"
    assert fn(12_300_000, "currency", "compact", locale="en_IN", currency="INR") == "₹1.2Cr"
    assert fn(1234.5, "number", locale="fr_FR", decimals=1) == f"1{NNBSP}234,5"
    assert fn(1500, "currency", locale="en_US", currency="JPY") == "¥1,500"
    assert fn(10, "currency", currency="XYZ") == f"XYZ{NBSP}10.00"


def test_settings_drive_defaults() -> None:
    with cfg.config(locale="en_IE", currency="EUR"):
        assert fn(10, "currency") == "€10.00"
    with pytest.warns(FormatWarning):
        assert fn(1.5, locale="sv_SE") == "1.5"


def test_durations() -> None:
    assert fn(3.2, "duration", duration_unit="days") == "3.2 days"
    assert fn(4.2, "duration", duration_unit="hours") == "4h 12m"
    assert fn(125, "duration") == "2m 5s"


def test_patterns() -> None:
    assert fn(1234.567, pattern="#,##0") == "1,235"
    assert fn(0.1234, pattern="0.0%") == "12.3%"
    assert fn(1234.5, pattern='"€"#,##0.00') == "€1,234.50"
    assert fn(-12.5, pattern='0.0" kg"') == "-12.5 kg"
    assert fn(1234.5, pattern="#,##0.0", locale="de_DE") == "1.234,5"


@pytest.mark.parametrize(
    "bad",
    ["{0.__class__}", "%s", "#,##0;[Red]", "<script>", "0" * 100, '"a\nb"0', '"' + "x" * 50 + '"0'],
)
def test_bad_patterns_are_rejected(bad: str) -> None:
    with pytest.raises(InvalidSpecError):
        parse_pattern(bad)


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=40))
def test_pattern_parser_never_crashes(pattern: str) -> None:
    try:
        p = parse_pattern(pattern)
    except InvalidSpecError:
        return
    assert 0 <= p.decimals <= 6


@settings(max_examples=300, deadline=None)
@given(
    st.floats(allow_nan=True, allow_infinity=True) | st.integers(-(10**15), 10**15),
    st.sampled_from(["currency", "percent", "pp", "count", "number", "duration"]),
    st.sampled_from(["compact", "full", "raw"]),
    st.sampled_from(["en_US", "de_DE", "en_IN", "fr_FR", "pt_BR"]),
)
def test_format_number_never_crashes(value: float, unit: str, style: str, locale: str) -> None:
    out = fn(value, unit, style, locale=locale)
    assert isinstance(out, str) and len(out) < 600  # full style of 1e300 is legitimately long
    if style == "compact" and abs(float(value)) < 1e15:
        assert len(out) < 30


def test_invalid_arguments() -> None:
    with pytest.raises(InvalidSpecError):
        fn(1, "money")
    with pytest.raises(InvalidSpecError):
        fn(1, decimals=9)
    with pytest.raises(InvalidSpecError):
        fn("abc")


def test_choose_decimals() -> None:
    assert choose_decimals([1, 2, 3]) == 0
    assert choose_decimals([1.5, 2000.25]) == 0
    assert choose_decimals([1.5, 20.25], "currency") == 2


def test_dates() -> None:
    ts = pd.Timestamp("2017-01-05 13:45:10")
    assert format_date(ts, "year") == "2017"
    assert format_date(ts, "quarter") == "Q1 2017"
    assert format_date(ts, "month") == "Jan 2017"
    assert format_date(ts, "month", "compact") == "Jan '17"
    assert format_date(ts, "day") == "Jan 5, 2017"
    assert format_date(ts, "day", locale="en_IE") == "5 Jan 2017"
    assert format_date(ts, "day", locale="de_DE") == "5 Jan. 2017"
    assert format_date(ts, "minute") == "Jan 5, 2017 13:45"
    assert format_date(ts, "week") == "W01 2017"
    assert format_date(pd.Timestamp("2017-04-10"), "quarter", fiscal_start=4) == "FY2018 Q1"
    assert format_date(pd.Timestamp("2017-03-10"), "year", fiscal_start=4) == "FY2017"
    assert format_date(None) == ""


def test_i18n() -> None:
    assert month_name(3, "fr", short=False) == "mars"
    assert text("top_n_of", n=10, total=17) == "Top 10 of 17"
    assert text("top_n_of", "de", n=10, total=17) == "Top 10 of 17"  # falls back to English
    assert text("sum_of", field="{0.__class__}") == "Sum of {0.__class__}"  # data stays data
    assert text("no_such_key") == "no_such_key"
