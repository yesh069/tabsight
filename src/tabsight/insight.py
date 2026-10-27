"""Plain-English insights, from fixed rules. Never an LLM, never a guess at causes.

Each rule states a fact the numbers show ("Sales peaked in Nov 2017"), never a reason
("because of the holiday sale"). Sentences come from templates in ``tabsight/i18n`` so
they can be translated, and every number in them is formatted like the charts.

Rules (PLAN section 13): peak and low, biggest contributor, concentration, negative
segments, trend direction, change against the previous period, outliers, seasonality.
Every threshold can be changed with ``thresholds={...}`` (see ``THRESHOLDS``).
"""

from __future__ import annotations

import dataclasses
import html
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from tabsight.aggregate import Measure, _numeric, _time_values, aggregate
from tabsight.analytics import NotEnoughData, linear_trend, outliers
from tabsight.formats import format_date, format_number
from tabsight.i18n import month_name, text
from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile
from tabsight.settings import resolve
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["THRESHOLDS", "Insight", "Insights", "insights"]

THRESHOLDS: dict[str, float] = {
    "contributor": 0.15,  # a value gives at least this share of the total
    "concentration": 0.5,  # the top 3 give at least this share
    "concentration_min_values": 6,  # ...out of at least this many values
    "trend_r2": 0.3,  # a straight line explains at least this much of the ups and downs
    "trend_min_change": 0.002,  # and moves at least 0.2% of the average per period
    "outlier_k": 3.0,  # "unusual" = beyond 3 box heights (IQR) from the middle half
    "outlier_max_share": 0.02,  # and at most 2% of rows (more is a distribution, not outliers)
    "seasonal_years": 2,  # full years needed before a month counts as "every year"
    "min_periods": 4,  # periods needed for peak, low and trend
    "max_per_kind": 2,  # at most this many insights of one kind (two peaks, two leaders...)
}
MAX_MEASURES = 3
MAX_DIMS = 3
MAX_CATEGORIES = 200  # dimensions with more distinct values are skipped (likely names or IDs)
ALL_DATA = "based on all data"
MINUS, EN_DASH = chr(0x2212), chr(0x2013)


@dataclasses.dataclass(frozen=True)
class Insight:
    """One sentence and the numbers behind it."""

    kind: str
    text: str
    score: float  # for ranking; higher first
    fields: tuple[str, ...]
    values: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    scope: str = ALL_DATA

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "fields": list(self.fields),
                "values": dict(self.values), "scope": self.scope}  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Insights(Sequence[Insight]):
    """The insights found, best first. Prints as a list; ``to_dict()`` for JSON."""

    items: tuple[Insight, ...]
    as_of: str | None = None

    def __getitem__(self, i: Any) -> Any:
        return self.items[i]

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[Insight]:
        return iter(self.items)

    @property
    def kinds(self) -> list[str]:
        return [i.kind for i in self.items]

    def show(self) -> str:
        if not self.items:
            return "No insights found: the numbers have no clear peak, trend, leader or outlier."
        return "\n".join(f"- {i.text}" for i in self.items)

    def __str__(self) -> str:
        return self.show()

    def _repr_html_(self) -> str:
        if not self.items:
            return f"<p>{html.escape(self.show())}</p>"
        return "<ul>" + "".join(f"<li>{html.escape(i.text)}</li>" for i in self.items) + "</ul>"

    def to_dict(self) -> dict[str, Any]:
        return {"as_of": self.as_of, "insights": [i.to_dict() for i in self.items]}


# ---------------------------------------------------------------- helpers


class _Words:
    """Formats numbers, periods and names the same way the charts do."""

    def __init__(self, prof: Profile, locale: str, currency: str, fiscal_start: int):
        self.prof, self.locale, self.currency, self.fiscal_start = (
            prof,
            locale,
            currency,
            fiscal_start,
        )

    def kwargs(self, m: Measure) -> dict[str, Any]:
        field = next((f for f in self.prof.fields if f.name == m.column), None)
        unit = (
            "count"
            if m.agg in ("count", "countd")
            else (field.unit if field and field.unit != "none" else "number")
        )
        kw: dict[str, Any] = {"unit": unit, "locale": self.locale}
        if unit == "currency":
            kw["currency"] = (field.currency if field else None) or self.currency
        if unit in ("percent", "pp") and field is not None and field.percent_scale:
            kw["percent_scale"] = field.percent_scale
        if unit == "duration" and field is not None and field.duration_unit:
            kw["duration_unit"] = field.duration_unit
        return kw

    def num(self, value: float, m: Measure) -> str:
        kw = self.kwargs(m)
        unit = kw.pop("unit")
        return format_number(value, unit, "compact", **kw)

    def pct(self, share: float, sign: bool = False) -> str:
        return format_number(
            share,
            "percent",
            "full",
            locale=self.locale,
            decimals=1 if abs(share) < 0.1 else 0,
            sign=sign,
        )

    def delta(self, current: float, previous: float, m: Measure) -> str:
        """``+14%``, or ``+0.5 pp`` for a rate: 12% -> 13% is up 1 point, not up 8%."""
        kw = self.kwargs(m)
        if kw["unit"] in ("percent", "pp"):
            out = format_number(current - previous, "pp", "full", locale=self.locale, decimals=1,
                                percent_scale=kw.get("percent_scale", "fraction"))  # fmt: skip
            return out if out.startswith(("-", MINUS, "+")) else "+" + out
        return self.pct(current / previous - 1, sign=True)

    def period(self, value: Any, grain: str) -> str:
        return format_date(value, grain, locale=self.locale, fiscal_start=self.fiscal_start)

    @staticmethod
    def name(column: str) -> str:
        return column.replace("_", " ")

    def measure(self, m: Measure) -> str:
        name = self.name(m.label)
        return {"sum": name, "mean": f"average {name}", "median": f"median {name}",
                "count": "the number of rows", "countd": f"distinct {name}"}.get(m.agg, name)  # fmt: skip

    @staticmethod
    def listing(items: list[str], more: int = 0) -> str:
        if more:
            return ", ".join(items) + text("ins_and_more", n=more)
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(key: str, **params: Any) -> str:
    out = text(key, **params)
    return out[:1].upper() + out[1:]


def _grain(dates: pd.Series) -> str:
    v = dates.dropna()
    span = (v.max() - v.min()).days if len(v) else 0
    if span <= 92:
        return "day"
    if span <= 6 * 366:
        return "month"
    if span <= 15 * 366:
        return "quarter"
    return "year"


# ---------------------------------------------------------------- rules over time


def _over_time(
    frame: pd.DataFrame, m: Measure, date: str, grain: str, w: _Words, th: Mapping[str, float]
) -> list[Insight]:
    result = aggregate(frame, [date], [m], freq={date: grain}, missing="zero", prof=w.prof)
    series = result.values.sort_values(date)
    if result.partial_period and len(series) > 1:
        series = series.iloc[:-1]  # a period that isn't over would look like a drop
    values = pd.to_numeric(series[m.label], errors="coerce").to_numpy(dtype="float64")
    periods = list(series[date])
    out: list[Insight] = []
    if len(values) < th["min_periods"] or not np.isfinite(values).any():
        return out
    what = w.measure(m)
    i = int(np.nanargmax(values))
    change = ""
    if i > 0 and np.isfinite(values[i - 1]) and values[i - 1] > 0:
        change = text("ins_vs", pct=w.delta(values[i], values[i - 1], m),
                      period=w.period(periods[i - 1], grain))  # fmt: skip
    out.append(Insight("peak", _sentence("ins_peak", measure=what, period=w.period(periods[i], grain),
                                         value=w.num(values[i], m), change=change),
                       70, (m.label, date), {"period": str(periods[i]), "value": float(values[i])}))  # fmt: skip
    j = int(np.nanargmin(values))
    if j != i and len(values) >= 6:
        out.append(Insight("low", _sentence("ins_low", measure=what, period=w.period(periods[j], grain),
                                            value=w.num(values[j], m)),
                           45, (m.label, date), {"period": str(periods[j]), "value": float(values[j])}))  # fmt: skip
    try:
        trend = linear_trend(values)
    except NotEnoughData:
        trend = None
    mean = float(np.nanmean(values))
    if trend is not None and mean > 0 and trend.r2 >= th["trend_r2"]:
        per = trend.slope / mean
        if abs(per) >= th["trend_min_change"]:
            out.append(Insight(
                "trend",
                _sentence("ins_trend_up" if per > 0 else "ins_trend_down", grain_adj=_ADJ[grain], measure=what,
                          pct=w.pct(abs(per)), grain=grain, start=w.period(periods[0], grain),
                          end=w.period(periods[-1], grain)),
                60 + 30 * trend.r2, (m.label, date),
                {"slope": trend.slope, "r2": trend.r2, "pct_per_period": per},
            ))  # fmt: skip
    if grain == "month":
        out += _seasonality(periods, values, m, date, w, th)
    return out


_ADJ = {
    "year": "yearly",
    "quarter": "quarterly",
    "month": "monthly",
    "week": "weekly",
    "day": "daily",
    "hour": "hourly",
}


def _seasonality(
    periods: list[Any],
    values: np.ndarray,
    m: Measure,
    date: str,
    w: _Words,
    th: Mapping[str, float],
) -> list[Insight]:
    when = pd.DatetimeIndex(periods)
    yrs, mos = np.asarray(when.year), np.asarray(when.month)
    table = pd.DataFrame({"year": yrs, "month": mos, "value": values})
    years = []
    for y in sorted(set(yrs.tolist())):
        g = table.loc[table["year"] == y, "value"]
        if len(g) == 12 and np.isfinite(g).all() and g.mean() > 0:
            years.append(int(y))
    if len(years) < th["seasonal_years"]:
        return []
    top = [set(table[table["year"] == y].nlargest(3, "value")["month"]) for y in years]
    every = sorted(int(mo) for mo in set.intersection(*top))
    if not every:
        return []
    index: dict[int, float] = {}
    for mo in every:
        ratios = []
        for y in years:
            year = table[table["year"] == y]
            ratios.append(
                float(year.loc[year["month"] == mo, "value"].iloc[0]) / float(year["value"].mean())
            )
        index[mo] = float(np.mean(ratios))
    best = max(every, key=lambda mo: index[mo])
    pair = [mo for mo in (best - 1, best + 1) if mo in every]
    months = sorted([best, *pair[:1]])
    label = EN_DASH.join(month_name(mo, w.locale.split("_")[0], short=False) for mo in months)
    return [Insight("seasonality", _sentence("ins_season", measure=w.measure(m), months=label,
                                             first=str(years[0]), last=str(years[-1])),
                    65, (m.label, date), {"months": months, "index": index[best], "years": years})]  # fmt: skip


def _change(frame: pd.DataFrame, m: Measure, date: str, w: _Words, as_of: Any, span_days: int,
            th: Mapping[str, float]) -> list[Insight]:  # fmt: skip
    from tabsight.periods import compare

    how = "previous_year" if span_days >= 365 + 31 else "previous_month"
    try:
        c = compare(frame, m.label if m.column else date, date, compare=how, as_of=as_of, agg=m.agg,
                    fiscal_start=w.fiscal_start, locale=w.locale, prof=w.prof)  # fmt: skip
    except InvalidSpecError:
        return []
    if c.pct is None or c.change is None:
        return []
    key = (
        "ins_change_up"
        if c.change > 0
        else ("ins_change_down" if c.change < 0 else "ins_change_flat")
    )
    if c.current is None or c.previous is None:
        return []
    size = w.delta(c.current, c.previous, m).lstrip("+-" + MINUS)
    return [Insight("change", _sentence(key, measure=w.measure(m), pct=size, current=c.current_label,
                                        previous=c.previous_label),
                    90 + min(abs(c.pct) * 100, 50), (m.label, date), c.to_dict())]  # fmt: skip


# ---------------------------------------------------------------- rules over categories


def _by_category(
    frame: pd.DataFrame, m: Measure, dim: str, w: _Words, th: Mapping[str, float]
) -> list[Insight]:
    result = aggregate(frame, [dim], [m], sort="desc", prof=w.prof)
    table = result.values.dropna(subset=[m.label])
    if len(table) < 2:
        return []
    names = [str(v) for v in table[dim]]
    values = table[m.label].to_numpy(dtype="float64")
    what, many = w.measure(m), w.name(dim)
    out: list[Insight] = []
    additive = m.agg in ("sum", "count")
    total = float(values.sum())
    if additive and (values >= 0).all() and total > 0:
        share = float(values[0]) / total
        if share >= th["contributor"] and len(values) >= 3:
            out.append(Insight("contributor", _sentence("ins_contributor", name=names[0], pct=w.pct(share), measure=what),
                               50 + 30 * share, (m.label, dim), {"name": names[0], "share": share}))  # fmt: skip
        top3 = float(values[:3].sum()) / total
        if len(values) >= th["concentration_min_values"] and top3 >= th["concentration"]:
            out.append(Insight("concentration", _sentence("ins_concentration", n=3, dim=many, pct=w.pct(top3),
                                                          measure=what, names=w.listing(names[:3])),
                               55 + 30 * top3, (m.label, dim), {"names": names[:3], "share": top3}))  # fmt: skip
    negative = [n for n, v in zip(names, values, strict=True) if v < 0]
    if negative and len(negative) < len(values) and m.agg in ("sum", "mean", "median"):
        shown = sorted(negative, key=lambda n: values[names.index(n)])[:3]
        out.append(Insight("negative", _sentence("ins_negative", k=len(negative), n=len(values), dim=many,
                                                 measure=what, names=w.listing(shown, len(negative) - len(shown))),
                           75, (m.label, dim), {"names": negative}))  # fmt: skip
    return out


def _outliers(frame: pd.DataFrame, m: Measure, w: _Words, th: Mapping[str, float]) -> list[Insight]:
    if m.column is None or m.agg in ("count", "countd"):
        return []
    values = _numeric(frame[m.column], w.prof[m.column].source)
    finite = values[np.isfinite(values)]
    if len(finite) < 20:
        return []
    mask = outliers(finite.to_numpy(), "iqr", th["outlier_k"])
    q1, q3 = np.percentile(finite, [25, 75])
    out = []
    for side, flagged in (
        ("large", mask & (finite.to_numpy() > q3)),
        ("small", mask & (finite.to_numpy() < q1)),
    ):
        k = int(flagged.sum())
        if not k or k > th["outlier_max_share"] * len(finite):
            continue
        edge = float(
            finite.to_numpy()[flagged].min()
            if side == "large"
            else finite.to_numpy()[flagged].max()
        )
        out.append(Insight("outliers", _sentence(f"ins_outliers_{side}", k=f"{k:,}", rows="row" if k == 1 else "rows",
                                                 measure=w.name(m.label), edge=w.num(edge, Measure(m.column, "sum"))),
                           40, (m.label,), {"count": k, "edge": edge, "side": side}))  # fmt: skip
    return out


# ---------------------------------------------------------------- entry point


def _names(value: Any) -> list[str]:
    return [] if value is None else ([value] if isinstance(value, str) else list(value))


def insights(
    data: Any,
    y: str | Sequence[str] | None = None,
    x: str | Sequence[str] | None = None,
    date: str | None = None,
    *,
    as_of: Any = None,
    max_items: int = 8,
    thresholds: Mapping[str, float] | None = None,
    locale: str | None = None,
    prof: Profile | None = None,
) -> Insights:
    """Plain-English facts about ``data``: peaks, trends, leaders, losses, outliers.

    With no fields given, tabsight picks up to three measures (``y``), three category
    columns (``x``) and the first date column. Every sentence is a fact the numbers
    show, never a cause. ``thresholds`` changes when a rule speaks up (see ``THRESHOLDS``).
    """
    if type(max_items) is not int or not 1 <= max_items <= 50:
        raise InvalidSpecError("max_items must be a whole number 1-50")
    th = dict(THRESHOLDS)
    for key, value in (thresholds or {}).items():
        if key not in THRESHOLDS:
            raise InvalidSpecError(
                f"unknown threshold {safe_repr(key)}; choose from {sorted(THRESHOLDS)}"
            )
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1000:
            raise InvalidSpecError(f"threshold {key} must be a number 0-1000")
        th[key] = float(value)
    settings = resolve(locale=locale)
    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    for name in [*_names(y), *_names(x), *([date] if date else [])]:
        if name not in prof:
            raise InvalidSpecError(f"column {safe_repr(name)} not found")
    ys = (
        _names(y)
        or [f.name for f in prof.fields if f.role == "measure" and f.agg in ("sum", "mean")][
            :MAX_MEASURES
        ]
    )
    xs = (
        _names(x)
        or [
            f.name
            for f in prof.fields
            if f.role == "dimension" and 2 <= f.distinct <= MAX_CATEGORIES
        ][:MAX_DIMS]
    )
    if date is None:
        date = next((f.name for f in prof.fields if f.role == "time"), None)
    elif prof[date].role != "time":
        raise InvalidSpecError(f"{safe_repr(date)} is not a date column")
    w = _Words(prof, settings.locale, settings.currency, settings.fiscal_start)
    if date is not None and as_of is not None:
        from tabsight.periods import reference_date

        when = _time_values(frame[date], prof, date)
        today, _ = reference_date(when, as_of)
        frame = frame[~(when.dt.normalize() > today)]  # nothing after "today" is described
    found: list[Insight] = []
    as_of_text = None
    for name in ys[:MAX_MEASURES]:
        field = prof[name]
        agg = field.agg if field.agg not in ("none", "wavg") else "count"
        if field.role != "measure":
            agg = "count"
        m = Measure(name if agg != "count" or field.role == "measure" else None, agg)
        if date is not None:
            dates = _time_values(frame[date], prof, date)
            if dates.notna().sum() >= 2:
                grain = _grain(dates)
                found += _over_time(frame, m, date, grain, w, th)
                span = int((dates.max() - dates.min()).days)
                change = _change(frame, m, date, w, as_of, span, th)
                found += change
                if change:
                    as_of_text = change[0].values["as_of"]
        for dim in xs[:MAX_DIMS]:
            if prof[dim].distinct <= MAX_CATEGORIES:
                found += _by_category(frame, m, dim, w, th)
        found += _outliers(frame, m, w, th)
    found.sort(key=lambda i: -i.score)
    kept: list[Insight] = []
    seen: set[tuple[Any, ...]] = set()
    per_kind: dict[str, int] = {}
    for item in found:
        # "Consumer makes up 54% of Sales" and "...of Quantity" say the same thing twice
        ident = (
            item.kind,
            *item.fields[1:],
            str(item.values.get("name", item.values.get("names", ""))),
        )
        if item.kind in ("contributor", "concentration", "negative") and ident in seen:
            continue
        if per_kind.get(item.kind, 0) >= th["max_per_kind"]:
            continue
        seen.add(ident)
        per_kind[item.kind] = per_kind.get(item.kind, 0) + 1
        kept.append(item)
    return Insights(tuple(kept[:max_items]), as_of_text)
