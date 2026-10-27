"""Period comparisons: this year against last year, this month against last month, and so on.

Rules:

- "Today" is the latest date in the data, never the computer's clock, so the result is
  the same on every run. ``as_of="2017-12-31"`` overrides it.
- The current window runs from the start of the period that holds "today" up to and
  including that day. It is compared with **the same window shifted back** one period,
  so a year that isn't over is compared with the same days of last year, never with a
  whole year.
- Fiscal years follow ``fiscal_start`` (``4`` = April), and quarters follow fiscal years.
- If the earlier window has no data, there is no change to report: the result says
  "no data for the previous year" instead of a misleading +100%.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pandas as pd

from tabsight.aggregate import Measure, _time_values, aggregate, bucket
from tabsight.formats import format_date
from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile
from tabsight.settings import resolve
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["COMPARES", "Comparison", "compare", "reference_date"]

MIN_SHARE = 0.25  # without as_of, a period so far must cover a quarter of it to be compared

COMPARES = {
    "previous_year": "year",
    "previous_quarter": "quarter",
    "previous_month": "month",
    "previous_period": None,  # the window just before, of the same length
}
_STEP = {"year": pd.DateOffset(years=1), "quarter": pd.DateOffset(months=3),
         "month": pd.DateOffset(months=1)}  # fmt: skip
_WORD = {"year": "year", "quarter": "quarter", "month": "month", None: "period"}


@dataclasses.dataclass(frozen=True)
class Comparison:
    """One measure in two windows. ``change`` and ``pct`` are None when there is nothing to compare."""

    measure: str
    agg: str
    current: float | None
    previous: float | None
    change: float | None
    pct: float | None  # change as a fraction of the previous value (0.141 = +14.1%)
    start: pd.Timestamp
    end: pd.Timestamp  # inclusive
    previous_start: pd.Timestamp
    previous_end: pd.Timestamp
    as_of: pd.Timestamp
    as_of_source: str  # "latest date in the data" or "as asked"
    current_label: str
    previous_label: str
    note: str | None = None

    def __str__(self) -> str:
        if self.change is None:
            return f"{self.measure}: {self.current_label} vs {self.previous_label}: {self.note}"
        pct = f"{self.pct:+.1%}" if self.pct is not None else "n/a"
        return f"{self.measure}: {self.current_label} vs {self.previous_label}: {pct}"

    def to_dict(self) -> dict[str, Any]:
        out = dataclasses.asdict(self)
        for key in ("start", "end", "previous_start", "previous_end", "as_of"):
            out[key] = out[key].date().isoformat()
        return out


def reference_date(dates: pd.Series, as_of: Any = None) -> tuple[pd.Timestamp, str]:
    """ "Today" for comparisons: ``as_of`` if given, else the latest date in the data."""
    if as_of is not None:
        try:
            ts = pd.Timestamp(as_of)
        except (ValueError, TypeError):
            raise InvalidSpecError(
                f"as_of={safe_repr(as_of)} must be a date like '2017-12-31'"
            ) from None
        if pd.isna(ts):
            raise InvalidSpecError("as_of must be a date, not missing")
        return ts.tz_localize(None).normalize() if ts.tzinfo else ts.normalize(), "as asked"
    v = pd.to_datetime(dates, errors="coerce")
    if getattr(v.dt, "tz", None) is not None:
        v = v.dt.tz_localize(None)
    latest = v.max()
    if pd.isna(latest):
        raise InvalidSpecError("there are no dates to compare periods with")
    return pd.Timestamp(latest).normalize(), "the latest date in the data"


def _window(
    as_of: pd.Timestamp, how: str, window: Any, fiscal_start: int, dates: pd.Series
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if window is not None:
        if not isinstance(window, list | tuple) or len(window) != 2:
            raise InvalidSpecError(
                "window must be (start, end), for example ('2017-03-01', '2017-05-31')"
            )
        try:
            start, end = (pd.Timestamp(w).normalize() for w in window)
        except (ValueError, TypeError):
            raise InvalidSpecError(
                f"window={safe_repr(window)} must hold two dates like '2017-03-01'"
            ) from None
        if pd.isna(start) or pd.isna(end):
            raise InvalidSpecError("window dates must not be missing")
        if end < start:
            raise InvalidSpecError("window must start before it ends")
        return start, end
    grain = COMPARES[how]
    if grain is None:
        first = pd.to_datetime(dates, errors="coerce").min()
        raise InvalidSpecError(
            "compare='previous_period' needs window=(start, end); "
            f"the data starts {pd.Timestamp(first).date()} and ends {as_of.date()}"
        )
    start = bucket(pd.Series([as_of]), grain, fiscal_start=fiscal_start).iloc[0]
    return pd.Timestamp(start), as_of


def _shift(start: pd.Timestamp, end: pd.Timestamp, how: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    grain = COMPARES[how]
    if grain is None:
        days = (end - start).days + 1
        return start - pd.DateOffset(days=days), start - pd.DateOffset(days=1)
    return start - _STEP[grain], end - _STEP[grain]


def _label(
    start: pd.Timestamp, end: pd.Timestamp, grain: str | None, fiscal_start: int, locale: str
) -> str:
    if grain is not None:
        period = format_date(start, grain, locale=locale, fiscal_start=fiscal_start)
        if _whole(start, end, grain, fiscal_start):
            return period
        return f"{period} to {format_date(end, 'day', locale=locale)}"
    return f"{format_date(start, 'day', locale=locale)} to {format_date(end, 'day', locale=locale)}"


def _whole(start: pd.Timestamp, end: pd.Timestamp, grain: str, fiscal_start: int) -> bool:
    """True when ``end`` is the last day of the period that starts at ``start``."""
    after = bucket(pd.Series([end + pd.DateOffset(days=1)]), grain, fiscal_start=fiscal_start).iloc[
        0
    ]
    return bool(after != start)


def _value(frame: pd.DataFrame, m: Measure, prof: Profile) -> float | None:
    if not len(frame):
        return None
    result = aggregate(frame, None, [m], prof=prof)
    v = result.values[m.label].iloc[0] if len(result.frame) else None
    if v is None or pd.isna(v):
        return None
    return float(v)


def compare(
    data: Any,
    y: str,
    date: str,
    *,
    compare: str = "previous_year",
    as_of: Any = None,
    window: Any = None,
    agg: str | None = None,
    fiscal_start: int | None = None,
    locale: str | None = None,
    prof: Profile | None = None,
) -> Comparison:
    """Compare ``y`` in the current window with the same window one period earlier.

    ``compare``: ``"previous_year"`` (year to date against the same days last year),
    ``"previous_quarter"``, ``"previous_month"``, or ``"previous_period"`` with
    ``window=(start, end)`` (that window against the one just before it, same length).
    ``window`` may also be given with the other choices, to compare a filtered range
    with the same range a year (quarter, month) earlier.
    """
    if compare not in COMPARES:
        raise InvalidSpecError(f"compare={safe_repr(compare)} must be one of {tuple(COMPARES)}")
    settings = resolve(fiscal_start=fiscal_start, locale=locale)
    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    for name in (y, date):
        if name not in prof:
            raise InvalidSpecError(f"column {safe_repr(name)} not found")
    field = prof[y]
    m = Measure(y, agg or (field.agg if field.agg not in ("none", "wavg") else "count"))
    if prof[date].role != "time":
        raise InvalidSpecError(
            f"{safe_repr(date)} is not a date column, so periods can't be compared"
        )
    dates = _time_values(frame[date], prof, date)
    today, source = reference_date(dates, as_of)
    start, end = _window(today, compare, window, settings.fiscal_start, dates)
    grain = COMPARES[compare] if window is None else None
    if as_of is None and grain is not None:
        period_days = (start + _STEP[grain] - start).days
        if (end - start).days + 1 < MIN_SHARE * period_days:
            # The data stops a few days into a new period ("2018" is Jan 1 alone): comparing
            # that sliver says little, so use the last complete period instead.
            stub = (end - start).days + 1
            today = start - pd.DateOffset(days=1)
            source = (f"the end of the last complete {grain} (the data has only {stub} day"
                      f"{'s' if stub != 1 else ''} of the next one)")  # fmt: skip
            start, end = _window(today, compare, None, settings.fiscal_start, dates)
    p_start, p_end = _shift(start, end, compare)
    if grain is not None and _whole(start, end, grain, settings.fiscal_start):
        # a whole month is compared with the whole month before
        p_end = start - pd.DateOffset(days=1)
    day = dates.dt.normalize()
    current = _value(frame[(day >= start) & (day <= end)], m, prof)
    previous = _value(frame[(day >= p_start) & (day <= p_end)], m, prof)
    word = _WORD[COMPARES[compare]]
    note, change, pct = None, None, None
    if previous is None:
        note = f"no data for the previous {word}"
    elif current is None:
        note = f"no data for the current {word}"
    else:
        change = current - previous
        pct = change / abs(previous) if previous != 0 else None
        if previous == 0:
            note = f"the previous {word} was zero, so there is no percentage change"
    return Comparison(
        y, m.agg, current, previous, change, pct, start, end, p_start, p_end, today, source,
        _label(start, end, grain, settings.fiscal_start, settings.locale),
        _label(p_start, p_end, grain, settings.fiscal_start, settings.locale), note,
    )  # fmt: skip
