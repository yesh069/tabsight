"""``ts.auto(df)``: a whole dashboard from a DataFrame in one line.

The choices follow fixed rules on the column profile (``ts.profile``), never a model,
so the same data always gives the same dashboard, and each choice is written down in
``dash.decisions``:

1. KPI cards for the main measures (money first), compared with the previous year when
   the dates cover more than a year. With no measures, the rows (or distinct IDs) are counted.
2. A line of the main measure over time, when there is a date.
3. A map, when a column holds countries, regions or cities.
4. Bars of the main measure by the categories with a handful of values.
5. Filters on the date and the smallest categories, and an insights panel.

Every tile is tried before it is added, and the dashboard is checked to fit the size
limit, dropping filters and then tiles if it does not. So ``ts.auto`` works on any table;
a table with nothing to chart gets a single table tile.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from tabsight.aggregate import _time_values
from tabsight.dashboard import Dashboard
from tabsight.io import as_frame
from tabsight.profile import Field, Profile, _prepare, profile
from tabsight.warnings import InvalidSpecError

__all__ = ["auto"]

MAX_KPIS = 4
MAX_BARS = 3
MAX_CATEGORY_VALUES = 50
MAX_FILTER_VALUES = 30
MAX_GEO_CHECKS = 6
_UNIT_ORDER = {"currency": 0, "count": 1, "none": 2, "duration": 3, "percent": 4}


def _measures(prof: Profile, frame: pd.DataFrame) -> list[Field]:
    found = [
        f
        for f in prof.fields
        if f.is_measure and f.missing < prof.rows and frame[f.name].nunique() > 1
    ]
    return sorted(
        found, key=lambda f: _UNIT_ORDER.get(f.unit, 5)
    )  # stable: column order breaks ties


def _time(prof: Profile, frame: pd.DataFrame) -> Field | None:
    for f in prof.fields:
        if f.role == "time" and frame[f.name].nunique() > 2:
            return f
    return None


def _place(prof: Profile, frame: pd.DataFrame) -> tuple[str, str] | None:
    """The column to map and its level. Countries and regions (filled maps) win over
    cities (points), so Superstore's State is mapped rather than its City."""
    from tabsight.geo import detect

    found: list[tuple[int, str, str]] = []
    checked = 0
    for f in prof.fields:
        if f.role != "dimension" or not 2 <= f.distinct <= 5000 or f.currency_code_column:
            continue
        checked += 1
        if checked > MAX_GEO_CHECKS:
            break
        try:
            target = detect(frame[f.name].dropna())
        except InvalidSpecError:
            continue
        if target is not None and target.share >= 0.8:
            found.append((target.level == "city", f.name, target.level))
    if not found:
        return None
    _, name, level = min(found, key=lambda t: t[0])  # stable: column order breaks ties
    return name, level


def _categories(prof: Profile, skip: set[str]) -> list[Field]:
    cats = [f for f in prof.fields if f.role == "dimension" and f.name not in skip and 2 <= f.distinct <= MAX_CATEGORY_VALUES
            and not f.currency_code_column]  # fmt: skip
    # A hierarchy's top level first (Region before State), then fewer values first.
    tops = {h[0] for h in prof.hierarchies}
    return sorted(cats, key=lambda f: (f.name not in tops, f.distinct))


def auto(
    data: Any,
    title: str | None = None,
    *,
    max_tiles: int = 10,
    insights: bool = True,
    theme: str | None = None,
    locale: str | None = None,
    currency: str | None = None,
) -> Dashboard:
    """A dashboard chosen from the data: KPIs, a trend, a map, bars, filters and insights.

    >>> ts.auto(df).to_html("dashboard.html")

    ``dash.decisions`` says what was chosen and why; the result is an ordinary
    :class:`Dashboard`, so you can add tiles, change filters or ``save`` it."""
    if type(max_tiles) is not int or not 1 <= max_tiles <= 40:
        raise InvalidSpecError("max_tiles must be a whole number 1-40")
    frame, _ = _prepare(as_frame(data))
    if frame.empty or not len(frame.columns):
        raise InvalidSpecError("the data has no rows")
    prof = profile(frame, quiet=True)
    measures = _measures(prof, frame)
    counted = None
    if not measures:  # count rows instead, with a column of ones on tabsight's own copy
        counted = next(
            n for n in ("Records", "Records (rows)", "__records") if n not in frame.columns
        )
        frame = frame.assign(**{counted: 1})
        prof = profile(frame, quiet=True)
        measures = [prof[counted]]
    when = _time(prof, frame)
    mapped = _place(prof, frame)
    place = mapped[0] if mapped else None
    cats = _categories(prof, {place} if place else set())
    decisions: list[str] = []
    tiles: list[tuple[str, dict[str, Any]]] = []

    main = measures[0].name
    if counted is None:
        decisions.append(
            "measures: " + ", ".join(f"{f.name} ({f.unit}, {f.agg})" for f in measures[:MAX_KPIS])
        )
    else:
        decisions.append(f"no measures found, so tiles count rows (as {counted})")
    if when is not None:
        dates = _time_values(frame[when.name], prof, when.name).dropna()
        span = (dates.max() - dates.min()).days if len(dates) else 0
        compare = "previous_year" if span and span > 400 else None
        freq = (
            "day"
            if span <= 92
            else "month"
            if span <= 6 * 366
            else "quarter"
            if span <= 15 * 366
            else "year"
        )
        decisions.append(
            f"date: {when.name}" + (" (KPIs compare with the previous year)" if compare else "")
        )
    else:
        compare, freq = None, None
    kpis = measures[:MAX_KPIS]
    width = 12 // max(1, len(kpis))
    for f in kpis:
        tiles.append(
            ("kpi", {"y": f.name, "w": width, **({"compare": compare} if compare else {})})
        )
    ids = [f for f in prof.fields if f.role == "id" and f.source == "text"]
    if counted is not None and ids:  # distinct orders, customers... next to the row count
        tiles.append(("kpi", {"y": ids[0].name, "w": width}))
    if when is not None:
        tiles.append(
            ("line", {"x": when.name, "y": main, "freq": freq, "w": 12 if not cats else 8})
        )
        if cats:
            first = cats[0]
            tiles.append(("donut" if first.distinct <= 6 and prof[main].agg == "sum" else "hbar",
                          {"x": first.name, "y": main, "w": 4}))  # fmt: skip
            cats = cats[1:]
    if place is not None:
        level = mapped[1] if mapped else ""
        tiles.append(
            (
                "symbol_map" if level == "city" else "map",
                {"geo": place, "y": main, "w": 6 if cats else 12},
            )
        )
        decisions.append(f"map: {place} holds {'cities' if level == 'city' else 'places'}")
    for f in cats[:MAX_BARS]:
        many = f.distinct > 6
        tiles.append(
            (
                "hbar" if many else "bar",
                {"x": f.name, "y": main, "w": 6, **({"top": 15} if f.distinct > 15 else {})},
            )
        )
    if len(tiles) <= len(kpis):  # nothing to chart: show the rows' first columns as a table
        cols = [f.name for f in prof.fields if f.role in ("dimension", "id")][:1]
        if cols:
            tiles.append(("table", {"x": cols[0], "y": main, "w": 12, "top": 50}))

    dash = Dashboard(
        title or "Dashboard", data=frame, theme=theme, locale=locale, currency=currency
    )
    for kind, args in tiles[:max_tiles]:
        args = {k: v for k, v in args.items() if v is not None}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from tabsight.charts import chart

                chart(frame, kind, prof=prof, **{k: v for k, v in args.items() if k != "w"})
        except InvalidSpecError as e:
            decisions.append(
                f"skipped {kind} of {args.get('x') or args.get('geo') or args.get('y')}: {e}"
            )
            continue
        dash.add(kind, **args)
    if not dash.tiles:
        raise InvalidSpecError("tabsight found nothing to chart in this data")

    filters = [when.name] if when is not None else []
    filters += [f.name for f in _categories(prof, set()) if f.distinct <= MAX_FILTER_VALUES][:2]
    if place is not None and place not in filters and prof[place].distinct <= MAX_FILTER_VALUES:
        filters.append(place)
    dash.filters = filters
    if insights and counted is None:
        dash.insights()
    _fit(dash, decisions)
    if dash.filters:
        decisions.append("filters: " + ", ".join(dash.filters))
    dash.decisions = decisions
    return dash


def _fit(dash: Dashboard, decisions: list[str]) -> None:
    """Make sure the dashboard builds within the size limit: drop filters, then tiles."""
    while True:
        try:
            dash.build()
            decisions.extend(
                f"to stay under the size limit, tabsight {step}" for step in dash.size_steps
            )
            return
        except InvalidSpecError as e:
            if "MB" not in str(e) or (not dash.filters and len(dash.tiles) <= 1):
                raise
            if len(dash.filters) > 1 or (dash.filters and len(dash.tiles) <= 1):
                gone = dash.filters.pop()
                decisions.append(f"dropped the {gone} filter to stay under the size limit")
            else:
                gone_tile = dash.tiles.pop()
                decisions.append(
                    f"dropped a {gone_tile.get('kind')} tile to stay under the size limit"
                )
