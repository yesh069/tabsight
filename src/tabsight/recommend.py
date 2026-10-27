"""``ts.recommend``: "Show Me" without an LLM.

Given the fields you picked, rank the chart kinds that fit, with a plain-English reason
for each and a reason for every kind that was ruled out. The rules look at what the
fields are (dates, categories, measures), how many values the categories have, how long
their labels are, whether the measure can be negative, and whether it adds up to a
whole (sums do; averages and distinct counts don't).

Deterministic: the same data and fields always give the same ranking.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import pandas as pd

from tabsight.aggregate import Measure, aggregate
from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile
from tabsight.spec import CHART_KINDS, ChartSpec, _name
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["Recommendation", "Recommendations", "recommend"]

LONG_LABEL = 16
MANY_CATEGORIES = 15
DONUT_MAX = 8
MAX_BARS = 50
TOP_BARS = 20
TOP_LINES = 6


@dataclasses.dataclass(frozen=True)
class Recommendation:
    kind: str
    score: int
    reason: str
    spec: ChartSpec
    available: bool  # True when ts.chart can draw it today
    phase: int | None = None  # the roadmap phase that adds it, when not available yet


@dataclasses.dataclass(frozen=True)
class Recommendations:
    """Ranked suggestions (best first) plus the kinds that were ruled out, with reasons."""

    items: tuple[Recommendation, ...]
    rejected: tuple[tuple[str, str], ...]
    fields: str

    def __iter__(self) -> Any:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> Recommendation:
        return self.items[i]

    @property
    def best(self) -> Recommendation:
        """The highest-scoring chart that can be drawn today."""
        for r in self.items:
            if r.available:
                return r
        raise InvalidSpecError(f"no chart available yet for {self.fields}")

    def show(self) -> str:
        lines = [f"Charts for {self.fields}:", ""]
        for r in self.items:
            when = "" if r.available else f"  (phase {r.phase})"
            lines.append(f"  {r.score:>3}  {r.kind:<15} {r.reason}{when}")
        if self.rejected:
            lines += ["", "Ruled out:"]
            lines += [f"       {kind:<15} {why}" for kind, why in self.rejected]
        return "\n".join(lines)

    def why_not(self, kind: str) -> str:
        """Why ``kind`` is not suggested (or where it ranks, if it is)."""
        from tabsight.spec import ALIASES

        kind = ALIASES.get(kind, kind)
        if kind not in CHART_KINDS:
            raise InvalidSpecError(f"unknown chart kind {safe_repr(kind)}")
        for r in self.items:
            if r.kind == kind:
                return f"{kind} is suggested with score {r.score}: {r.reason}"
        return dict(self.rejected).get(kind, f"{kind} does not fit {self.fields}")

    def __str__(self) -> str:
        return self.show()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "items": [
                {
                    "kind": r.kind,
                    "score": r.score,
                    "reason": r.reason,
                    "available": r.available,
                    "phase": r.phase,
                    "spec": r.spec.to_dict(),
                }
                for r in self.items
            ],
            "rejected": [{"kind": k, "reason": why} for k, why in self.rejected],
        }


@dataclasses.dataclass
class _Fields:
    times: list[str]
    cats: list[str]
    measures: list[Measure]
    prof: Profile
    frame: pd.DataFrame
    card: dict[str, int] = dataclasses.field(default_factory=dict)
    longest: dict[str, int] = dataclasses.field(default_factory=dict)
    negative: bool = False
    additive: bool = True
    periods: int = 0
    freq: str | None = None
    hierarchy: bool = False
    swapped: bool = False
    layout: dict[str, tuple[str, str | None]] = dataclasses.field(default_factory=dict)


def _names(value: str | Sequence[str] | None, what: str) -> list[str]:
    if value is None:
        return []
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list | tuple) or len(items) > 20:
        raise InvalidSpecError(f"{what} must be a column name or a list of up to 20")
    return [_name(v, what) for v in items]


def _suggest_freq(dates: pd.Series) -> str | None:
    values = pd.to_datetime(dates, errors="coerce").dropna()
    if values.empty:
        return None
    span = (values.max() - values.min()).days
    if span <= 92:
        return "day"
    if span <= 3 * 366:
        return "month"
    if span <= 10 * 366:
        return "quarter"
    return "year"


def recommend(
    data: Any,
    x: str | Sequence[str] | None = None,
    y: str | Sequence[str] | None = None,
    color: str | None = None,
    *,
    prof: Profile | None = None,
) -> Recommendations:
    """Rank the charts that fit these fields. ``x`` and ``color`` are what you group by,
    ``y`` the measure(s)."""
    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    dims = _names(x, "x") + _names(color, "color")
    ys = _names(y, "y")
    if not dims and not ys:
        raise InvalidSpecError("pick at least one column: x= to group by and/or y= to measure")
    for name in dims + ys:
        if name not in prof:
            import difflib

            hint = difflib.get_close_matches(name, prof.names(), n=1)
            raise InvalidSpecError(
                f"column {safe_repr(name)} not found"
                + (f"; did you mean {safe_repr(hint[0])}?" if hint else "")
            )
    if len(set(dims + ys)) != len(dims + ys):
        raise InvalidSpecError("each column can be used once (in x, color or y)")

    measures = []
    for name in ys:
        field = prof[name]
        agg = (
            field.agg
            if field.role == "measure" and field.agg in ("sum", "mean", "median", "min", "max")
            else "countd"
        )
        if field.role == "measure" and field.agg == "count":
            agg = "sum"
        measures.append(Measure(name, agg))
    f = _Fields(
        times=[d for d in dims if prof[d].role == "time"],
        cats=[d for d in dims if prof[d].role != "time"],
        measures=measures,
        prof=prof,
        frame=frame,
    )
    _measure_facts(f)
    candidates, rejected = _rules(f)

    from tabsight.charts import _LATER, DRAWN_KINDS

    best: dict[str, tuple[int, str]] = {}
    for kind, score, reason in candidates:  # a kind suggested twice keeps its higher score
        if kind not in best or score > best[kind][0]:
            best[kind] = (max(0, min(100, score)), reason)
    items = [
        Recommendation(
            kind, score, reason, _spec_for(kind, f), kind in DRAWN_KINDS, _LATER.get(kind)
        )
        for kind, (score, reason) in best.items()
    ]
    order = {k: i for i, k in enumerate(CHART_KINDS)}
    items.sort(key=lambda r: (-r.score, order.get(r.kind, 99)))
    ruled_out = sorted(
        {k: why for k, why in rejected if k not in best}.items(),
        key=lambda kv: order.get(kv[0], 99),
    )
    return Recommendations(tuple(items), tuple(ruled_out), _describe(f))


def _describe(f: _Fields) -> str:
    parts = []
    if f.times:
        parts.append(f"{len(f.times)} date field" + ("s" if len(f.times) > 1 else ""))
    if f.cats:
        parts.append(f"{len(f.cats)} category field" + ("s" if len(f.cats) > 1 else ""))
    parts.append(f"{len(f.measures)} measure" + ("s" if len(f.measures) != 1 else ""))
    return ", ".join(parts)


def _measure_facts(f: _Fields) -> None:
    for d in f.cats:
        values = f.frame[d].dropna().astype(str)
        f.card[d] = int(values.nunique())
        f.longest[d] = int(values.str.len().max()) if len(values) else 0
    if f.times:
        f.freq = (
            _suggest_freq(f.frame[f.times[0]]) if f.prof[f.times[0]].grain != "year" else "year"
        )
    f.additive = bool(f.measures) and all(m.agg == "sum" for m in f.measures)
    if len(f.cats) == 2:
        a, b = f.cats
        pair = f.frame[[a, b]].dropna()
        f.hierarchy = bool(len(pair)) and (
            pair.groupby(b, observed=True)[a].nunique().max() == 1
            or pair.groupby(a, observed=True)[b].nunique().max() == 1
        )
        if f.hierarchy:
            f.cats = sorted(f.cats, key=lambda c: f.card[c])  # parent first, then child
        elif f.card[b] > DONUT_MAX and f.card[a] < f.card[b]:
            f.cats = [b, a]  # the field with fewer values goes in the colours
            f.swapped = True
    if not f.measures:
        return
    dims = f.times[:1] + f.cats
    result = aggregate(
        f.frame, dims or None, f.measures[:1], freq=f.freq, missing="connect", prof=f.prof
    )
    values = pd.to_numeric(result.values[f.measures[0].label], errors="coerce").fillna(0)
    f.negative = bool((values.to_numpy(dtype=float) < 0).any())
    if f.times:
        f.periods = int(result.values[f.times[0]].nunique())


def _rules(f: _Fields) -> tuple[list[tuple[str, int, str]], list[tuple[str, str]]]:
    c: list[tuple[str, int, str]] = []
    r: list[tuple[str, str]] = []
    nt, nc, nm = len(f.times), len(f.cats), len(f.measures)
    whole = f.additive and not f.negative
    why_not_whole = (
        "negative values can't be slices of a whole" if f.negative
        else "these values are averages or distinct counts, which don't add up to a whole"
    )  # fmt: skip

    if nt + nc > 2 or nt > 1:
        c.append(("table", 75, "several fields at once read best as a table"))
        r.append(("bar", "too many fields to group by for one chart"))
        return c, r

    if nm == 0:
        c.append(("table", 70, "no measure was picked, so a table lists the values"))
        r.append(("kpi", "a KPI needs a measure"))
        return c, r

    if nt == 0 and nc == 0:
        if nm == 1:
            c += [("kpi", 95, "one measure and nothing to group by: one number says it best"),
                  ("gauge", 45, "a gauge works if there is a target to compare with"),
                  ("table", 20, "a one-cell table works, but a KPI card is clearer")]  # fmt: skip
        else:
            c += [("scatter", 85, "two measures: a scatter plot shows how they relate"),
                  ("table", 65, "a small table lists each total side by side")]  # fmt: skip
        r.append(("bar", "nothing to group by: pick an x column for bars"))
        return c, r

    if nt == 1 and nc == 0 and f.periods == 1:
        c.append(("bar", 85, "there is only one period, and a line needs at least two points"))
        c.append(("kpi", 70, "one period: a single number says it"))
        c.append(("table", 30, "a table lists the value"))
        r.append(("line", "a line needs at least two periods; this data has one"))
        return c, r

    if nt == 1 and nc == 0:
        few = f.periods <= 12
        if nm == 1:
            c.append(("line", 95, "a date and a measure: a line shows the trend"))
            if whole:
                c.append(("area", 78, "an area also works because the values add up"))
            else:
                r.append(("area", "an area implies the values add up, and these don't"))
            c.append(("bar", 74 if few else 52, "with only a few periods, bars compare them directly" if few
                      else "bars work, but with many periods a line reads better"))  # fmt: skip
            c.append(("sparkline", 40, "a compact trend for a dashboard tile"))
            if f.freq == "day" and f.periods > 60:
                c.append(("calendar_heatmap", 55, "daily values: a calendar shows weekly patterns"))
            c.append(("table", 25, "a table lists every period"))
        else:
            units = {f.prof[m.column].unit for m in f.measures if m.column}
            if len(units) > 1:
                c.append(
                    ("combo", 90, "different units: bars and a line on two axes keep both readable")
                )
                c.append(
                    ("line", 70, "one line each, but the units differ, so one line may look flat")
                )
            else:
                c.append(("line", 88, "several measures over time: one line each"))
            c.append(("table", 30, "a table lists every period"))
        r.append(("donut", "a donut shows parts of a whole at one moment, not change over time"))
        r.append(("kpi", "a KPI shows one number; you picked a date to group by"))
        return c, r

    if nt == 1 and nc == 1:
        card = f.card[f.cats[0]]
        lines_ok = card <= 8
        c.append(
            (
                "multi_line",
                92 if lines_ok else 80,
                f"one line per {f.cats[0]}"
                if lines_ok
                else f"one line for each of the {TOP_LINES} biggest {f.cats[0]} values, the rest grouped as Other",
            )
        )
        if whole and card <= 8:
            c.append(
                (
                    "stacked_area",
                    80,
                    "the values add up, so stacked areas show the total and the mix",
                )
            )
        elif not whole:
            r.append(("stacked_area", why_not_whole))
        if whole and f.periods <= 12:
            c.append(
                (
                    "stacked_bar",
                    72,
                    "few periods: stacked bars show the total and the mix per period",
                )
            )
        if f.periods <= 6 and card <= 5:
            c.append(
                ("grouped_bar", 58, "few periods and categories: side-by-side bars compare them")
            )
        if card > 8 or f.periods > 24:
            c.append(("heatmap", 70, "many periods or categories: a heatmap shows the whole grid"))
        c.append(("table", 30, "a table lists every combination"))
        r.append(("donut", "a donut can't show change over time"))
        return c, r

    if nc == 1 and nm == 1:
        d = f.cats[0]
        card, long = f.card[d], f.longest[d] > LONG_LABEL
        is_id = f.prof[d].role == "id"
        numeric = f.prof[d].role == "measure"
        r.append(("line", "a line implies an order between categories; use bars"))
        if numeric:
            c.append(
                ("scatter", 86, f"{d} is a number too: a scatter plot shows how the two relate")
            )
            if card > MANY_CATEGORIES:
                c.append(
                    ("table", 60, f"{d} has {card} different values, too many for one bar each")
                )
                r.append(("bar", f"{d} has {card} different values, too many for one bar each"))
            else:
                c.append(("bar", 80, f"{d} is a number, so the bars keep its numeric order"))
                c.append(("table", 40, "a table lists exact values"))
            r.append(("donut", f"{d} is a number, not a set of parts"))
            return c, r
        place = None if is_id or card < 2 else _place(f, d)  # one place is a number, not a map
        if place is not None and place.level in ("country", "region"):
            c.append(("choropleth", 93, f"{d} holds places ({place.label}): a map shows where"))
        elif place is not None:
            c.append(
                (
                    "symbol_map",
                    85,
                    f"{d} holds cities: circles on a map show where, bars compare better",
                )
            )
        if is_id:
            c.append(
                (
                    "table",
                    80,
                    f"{d} looks like an ID, so grouping by it gives one bar per row; a table reads better",
                )
            )
        penalty = 30 if is_id else 0
        if card > MAX_BARS:
            c.append(
                (
                    "hbar",
                    70 - penalty,
                    f"{card} categories: horizontal bars of the top {TOP_BARS}, the rest grouped as Other",
                )
            )
            r.append(("bar", f"{card} categories are too many for upright bars"))
        elif long or card > MANY_CATEGORIES:
            c.append(
                (
                    "hbar",
                    92 - penalty,
                    "long labels or many categories: horizontal bars keep every label readable",
                )
            )
            c.append(("bar", 60 - penalty, "vertical bars would need rotated or crowded labels"))
        else:
            c.append(
                (
                    "bar",
                    90 - penalty,
                    "a measure by category: bars, largest first, are easiest to compare",
                )
            )
            c.append(("hbar", 80 - penalty, "horizontal bars work too, and suit longer labels"))
        if not whole:
            r.append(("donut", why_not_whole))
            r.append(("treemap", why_not_whole))
        elif card <= 6:
            c.append(
                ("donut", 76 - penalty, f"only {card} parts of a whole: a donut shows each share")
            )
        elif card <= DONUT_MAX:
            c.append(("donut", 62 - penalty, f"{card} slices is the most a donut should have"))
        elif card <= MANY_CATEGORIES:
            c.append(
                (
                    "donut",
                    40 - penalty,
                    f"{card} slices is too many; tabsight would keep 7 and group the rest",
                )
            )
        else:
            r.append(("donut", f"{card} slices are far too many to compare"))
        if whole and card >= 8:
            c.append(("treemap", 72 - penalty, "many parts of a whole: a treemap fits them all"))
            c.append(
                (
                    "pareto",
                    58 - penalty,
                    "a Pareto chart shows how few categories make most of the total",
                )
            )
        if card <= MAX_BARS:
            c.append(("lollipop", 50 - penalty, "a lighter alternative to bars"))
        if card == 1:
            c.append(("kpi", 85, "only one category: a single number is clearer"))
        c.append(("table", 40, "a table lists exact values"))
        return c, r

    if nc == 2 and nm == 1:
        a, b = f.cats
        ca, cb = f.card[a], f.card[b]
        if f.hierarchy:
            # nested: every b belongs to one a (f.cats is ordered parent, child)
            r.append(
                (
                    "grouped_bar",
                    f"{b} sits inside {a}, so side-by-side bars would be mostly empty slots",
                )
            )
            r.append(
                ("stacked100_bar", f"{b} sits inside {a}, so every 100% bar would be one colour")
            )
            if whole:
                c.append(("treemap", 88, f"{a} and {b} are nested, so a treemap shows both levels"))
                c.append(("sunburst", 74, "a sunburst also shows the two levels"))
            if ca <= 10 and cb <= MANY_CATEGORIES and f.longest[b] <= LONG_LABEL:
                f.layout["stacked_bar"] = (b, a)
                c.append(("stacked_bar", 80, f"one bar per {b}, coloured by the {a} it belongs to"))
            elif whole and cb <= 8:
                c.append(
                    ("stacked_bar", 82, f"totals per {a}, each split into the {b} values inside it")
                )
            c.append(("table", 55, "a table lists every combination"))
            r.append(("donut", "a donut shows one split, not two"))
            return c, r
        swap = f"; {b} has fewer values, so it goes in the colours" if f.swapped else ""
        if whole and cb <= 8:
            c.append(("stacked_bar", 85, f"totals per {a}, split by {b}{swap}"))
            c.append(("stacked100_bar", 72, f"compares the mix of {b} within each {a}"))
        elif not whole:
            r.append(("stacked_bar", why_not_whole))
            r.append(("stacked100_bar", why_not_whole))
        crowded = "" if cb <= 4 else f"; {cb} bars per group is crowded"
        if cb > 10:
            crowded += ", and more than 10 colours can't be told apart"
        c.append(
            (
                "grouped_bar",
                80 if cb <= 4 else (58 if cb <= 10 else 35),
                f"side-by-side bars compare each {b} directly{crowded}",
            )
        )
        if ca >= 5 and cb >= 5:
            c.append(
                ("heatmap", 78, "two categories with many values: a heatmap shows the whole grid")
            )
        c.append(("table", 55, "a table lists every combination"))
        r.append(("donut", "a donut shows one split, not two"))
        return c, r

    if nc == 1 and nm >= 2:
        d = f.cats[0]
        units = {f.prof[m.column].unit for m in f.measures if m.column}
        if len(units) == 1 and nm <= 4:
            c.append(("grouped_bar", 80, "measures in the same unit side by side"))
        else:
            c.append(("combo", 82, "different units: bars and a line on two axes"))
        if nm == 2 and f.card[d] >= 10:
            c.append(
                (
                    "scatter",
                    84 if f.card[d] >= 15 else 75,
                    f"one dot per {d} shows how the two measures relate",
                )
            )
        if nm == 3:
            c.append(("bubble", 78, "two measures as position and a third as size"))
        c.append(("table", 60, "a table lists every value"))
        return c, r

    c.append(("table", 60, "a table fits any combination of fields"))
    return c, r


def _place(f: _Fields, column: str) -> Any:
    """The map a column belongs on, or None (column values are looked up offline)."""
    from tabsight.geo.detection import SUGGEST_SHARE, detect

    return detect(f.frame[column], name=column, min_share=SUGGEST_SHARE)


def _spec_for(kind: str, f: _Fields) -> ChartSpec:
    ys = [m.column for m in f.measures if m.column]
    y: str | tuple[str, ...] | None = (ys[0] if len(ys) == 1 else tuple(ys)) if ys else None
    if kind in ("choropleth", "symbol_map"):
        return ChartSpec(kind, geo=f.cats[0], y=y)
    options = {"freq": f.freq} if f.times and f.freq else {}
    if kind in ("kpi", "gauge", "scatter", "bubble") and not (f.times or f.cats):
        return ChartSpec(kind, y=y)
    if kind == "table":
        dims = tuple(f.times + f.cats)
        return ChartSpec(kind, x=dims or None, y=y, options=options)
    x = f.times[0] if f.times else (f.cats[0] if f.cats else None)
    color = None
    if f.times and f.cats:
        color = f.cats[0]
    elif len(f.cats) == 2:
        color = f.cats[1]
    if kind in f.layout:
        x, color = f.layout[kind]
    top = None
    if kind == "multi_line" and color and f.card.get(color, 0) > 8:
        top = TOP_LINES
    elif kind == "hbar" and x in f.card and f.card[x] > MAX_BARS:
        top = TOP_BARS
    numeric_x = x is not None and not f.times and f.prof[x].role == "measure"
    sort = "none" if numeric_x and kind in ("bar", "hbar", "lollipop") else None
    return ChartSpec(kind, x=x, y=y, color=color, top=top, sort=sort, options=options)
