"""Reading values without changing the user's data: dates, numbers stored as text, units.

Every function returns new objects plus a note of what it assumed. Regexes are anchored
and have no nested quantifiers, so they run in linear time on any input.
"""

from __future__ import annotations

import dataclasses
import re

import numpy as np
import pandas as pd

__all__ = [
    "DateReading",
    "NumberReading",
    "read_dates",
    "read_numbers",
    "sample",
    "unit_from_name",
]

MAX_TEXT_LEN = 200  # longer strings are never treated as dates or numbers
_MAJORITY = 0.5  # share needed for structural choices (year-first, two-digit years...)
SAMPLE_ROWS = 10_000


def sample(series: pd.Series, n: int = SAMPLE_ROWS) -> pd.Series:
    """Deterministic, evenly spaced sample of the non-missing values."""
    values = series.dropna()
    if len(values) <= n:
        return values
    step = len(values) / n
    positions = np.array([int(i * step) for i in range(n)], dtype=np.int64)
    return values.iloc[positions]


# ---------------------------------------------------------------- dates


@dataclasses.dataclass(frozen=True)
class DateReading:
    values: pd.Series  # datetime64 series (NaT where not parsed)
    format: str  # strptime format used, or "datetime" when already datetime
    dayfirst: bool | None  # None when the format has no day/month question
    assumed: bool  # True when the day/month order came from settings, not the data
    success: float  # share of non-missing inputs that parsed
    failed_examples: tuple[str, ...]


_NUMERIC_DATE = re.compile(
    r"(?P<a>\d{1,4})[-/.](?P<b>\d{1,2})[-/.](?P<c>\d{1,4})"
    r"(?:[ T](?P<time>\d{1,2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?))?"
)
_TEXT_FORMATS = (
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%b %Y",
    "%B %Y",
    "%Y-%m",
    "%Y%m%d",
)


def read_dates(
    series: pd.Series, dayfirst: bool | None = None, threshold: float = 0.95
) -> DateReading | None:
    """Try to read a column as dates. Returns None if fewer than ``threshold`` parse.

    Day/month order comes from the data when any value proves it (a first number above
    12 means day-first). Otherwise ``dayfirst`` is used and the reading is marked as
    assumed; if ``dayfirst`` is None, month-first is assumed.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return DateReading(series, "datetime", None, False, 1.0, ())
    if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return None
    raw = series.dropna()
    if raw.empty:
        return None
    text = raw.astype(str).str.strip()
    if (text.str.len() > MAX_TEXT_LEN).any():
        return None
    probe = sample(text)

    # Structural choices use a fixed majority, never the caller's success threshold:
    # with threshold=0 ("parse what you can") every test would otherwise pass.
    numeric = probe.str.fullmatch(_NUMERIC_DATE)
    if numeric.mean() >= _MAJORITY:
        return _read_numeric_dates(series, text, dayfirst, threshold)

    best_fmt, best_rate = None, 0.0
    for fmt in _TEXT_FORMATS:
        rate = float(pd.to_datetime(probe, format=fmt, errors="coerce").notna().mean())
        if rate > best_rate:
            best_fmt, best_rate = fmt, rate
    if best_fmt is not None and best_rate >= max(threshold, 1e-9):
        full = pd.to_datetime(text, format=best_fmt, errors="coerce")
        return _result(series, text, full, best_fmt, None, False, threshold)
    return None


def _read_numeric_dates(
    series: pd.Series, text: pd.Series, dayfirst: bool | None, threshold: float
) -> DateReading | None:
    parts = text.str.extract(_NUMERIC_DATE)
    a = pd.to_numeric(parts["a"], errors="coerce")
    b = pd.to_numeric(parts["b"], errors="coerce")
    has_time = parts["time"].notna().any()
    if (parts["a"].str.len() == 4).mean() >= _MAJORITY:
        order, first, assumed = "%Y/%m/%d", None, False
    else:
        day_first_proof = bool((a > 12).any())
        month_first_proof = bool((b > 12).any())
        if day_first_proof and month_first_proof:
            return None  # contradictory: not a consistent date column
        if day_first_proof or month_first_proof:
            first, assumed = day_first_proof, False
        else:
            first, assumed = bool(dayfirst), True
        year2 = (parts["c"].str.len() == 2).mean() >= _MAJORITY
        yy = "%y" if year2 else "%Y"
        order = f"%d/%m/{yy}" if first else f"%m/%d/{yy}"
    normal = parts["a"] + "/" + parts["b"] + "/" + parts["c"]
    if has_time:
        times = parts["time"].fillna("00:00")
        times = times.where(times.str.count(":") == 2, times + ":00")
        normal = normal + " " + times
        fmt = order + " %H:%M:%S"
        parsed = pd.to_datetime(normal, format=fmt, errors="coerce")
        # fractional seconds
        frac = pd.to_datetime(normal, format=fmt + ".%f", errors="coerce")
        parsed = parsed.fillna(frac)
    else:
        fmt = order
        parsed = pd.to_datetime(normal, format=fmt, errors="coerce")
    return _result(series, text, parsed, fmt, first, assumed, threshold)


def _result(
    series: pd.Series,
    text: pd.Series,
    parsed: pd.Series,
    fmt: str,
    dayfirst: bool | None,
    assumed: bool,
    threshold: float,
) -> DateReading | None:
    success = float(parsed.notna().mean()) if len(parsed) else 0.0
    if success < threshold:
        return None
    failed = tuple(text[parsed.isna()].head(3).tolist())
    full = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    full.loc[parsed.index] = parsed
    return DateReading(full, fmt, dayfirst, assumed, success, failed)


# ---------------------------------------------------------------- numbers stored as text


@dataclasses.dataclass(frozen=True)
class NumberReading:
    values: pd.Series  # float64
    unit: str  # "currency", "percent" or "number"
    currency_symbol: str | None
    decimal: str  # "." or ","
    success: float
    failed_examples: tuple[str, ...]


_CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "¥": "JPY",
    "₩": "KRW",
    "₽": "RUB",
}
_NUM_TEXT = re.compile(
    r"(?P<neg1>\()?\s*(?P<sign>[-+−])?\s*(?P<pre>[$€£₹¥₩₽])?\s*(?P<sign2>[-+−])?\s*"
    r"(?P<num>\d[\d.,'   ]{0,30})\s*(?P<post>[$€£₹¥₩₽%])?\s*(?P<neg2>\))?"
)


def read_numbers(series: pd.Series, threshold: float = 0.95) -> NumberReading | None:
    """Read numbers stored as text: ``"$1,234.50"``, ``"15%"``, ``"(500)"``, ``"1.234,5 €"``."""
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return None
    raw = series.dropna()
    if raw.empty:
        return None
    text = raw.astype(str).str.strip()
    if (text.str.len() > 40).any():
        return None
    parts = text.str.extract(_NUM_TEXT)
    matched = text.str.fullmatch(_NUM_TEXT)
    if matched.mean() < threshold:
        return None
    nums = parts["num"].str.replace(r"['   ]", "", regex=True)
    decimal = _decimal_separator(nums.dropna())
    if decimal == ",":
        clean = nums.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        clean = nums.str.replace(",", "", regex=False)
    values = pd.to_numeric(clean, errors="coerce")
    negative = (
        parts["neg1"].notna() & parts["neg2"].notna()
        | parts["sign"].isin(["-", "−"])
        | parts["sign2"].isin(["-", "−"])
    )
    values = values.where(~negative, -values)
    symbols = pd.concat([parts["pre"], parts["post"]]).dropna()
    unit, symbol = "number", None
    if (symbols == "%").any() and (symbols == "%").mean() >= 0.5:
        unit = "percent"
    else:
        money = symbols[symbols != "%"]
        if not money.empty:
            unit, symbol = "currency", str(money.mode().iloc[0])
    has_symbol_or_separator = bool(symbols.size) or nums.str.contains(r"[.,]").any()
    if unit == "number" and not has_symbol_or_separator:
        return None  # plain integers as text: leave to the caller (may be codes)
    success = float(values.notna().mean())
    if success < threshold:
        return None
    full = pd.Series(np.nan, index=series.index, dtype="float64")
    full.loc[values.index] = values.astype("float64")
    failed = tuple(text[values.isna()].head(3).tolist())
    return NumberReading(full, unit, symbol, decimal, success, failed)


def _decimal_separator(nums: pd.Series) -> str:
    """Majority vote: the last separator followed by 1-2 digits, or ',' + 3 digits patterns."""
    comma_dec = nums.str.fullmatch(r"\d{1,3}(\.\d{3})*,\d{1,2}|\d+,\d{1,2}").sum()
    dot_dec = nums.str.fullmatch(r"\d{1,3}(,\d{3})*\.\d+|\d+\.\d+").sum()
    return "," if comma_dec > dot_dec else "."


def currency_code_for_symbol(symbol: str | None) -> str | None:
    return _CURRENCY_SYMBOLS.get(symbol or "")


# ---------------------------------------------------------------- units from column names

_NAME_UNIT_PATTERNS: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
    (re.compile(r"\((?:€|eur)\)|[_ ]eur$", re.I), "currency", "EUR"),
    (re.compile(r"\((?:\$|usd)\)|[_ ]usd$", re.I), "currency", "USD"),
    (re.compile(r"\((?:£|gbp)\)|[_ ]gbp$", re.I), "currency", "GBP"),
    (re.compile(r"\((?:₹|inr)\)|[_ ]inr$", re.I), "currency", "INR"),
    (re.compile(r"\((?:¥|jpy)\)|[_ ]jpy$", re.I), "currency", "JPY"),
    (re.compile(r"\(%\)|[_ ](pct|percent)$|%$", re.I), "percent", None),
    (re.compile(r"[_ ](hrs?|hours?)$|\((hrs?|hours?)\)", re.I), "duration", "hours"),
    (re.compile(r"[_ ](mins?|minutes?)$|\((mins?|minutes?)\)", re.I), "duration", "minutes"),
    (re.compile(r"[_ ](secs?|seconds?)$|\((secs?|seconds?)\)", re.I), "duration", "seconds"),
    (re.compile(r"[_ ]days$|\(days\)", re.I), "duration", "days"),
)


def unit_from_name(name: str) -> tuple[str, str | None] | None:
    """Unit written in the column name: ``Sales (€)``, ``Price_USD``, ``Duration_hrs``."""
    text = name.strip()[:MAX_TEXT_LEN]
    for pattern, unit, detail in _NAME_UNIT_PATTERNS:
        if pattern.search(text):
            return unit, detail
    return None
