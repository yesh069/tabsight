"""``ts.chart``: from a DataFrame to a finished, BI-quality chart.

Draws all 33 kinds in ``tabsight.spec.CHART_KINDS``, plus small multiples.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from tabsight.aggregate import OTHER_FLAG, Aggregation, Measure, aggregate
from tabsight.charts import _build
from tabsight.colors import ColorRegistry
from tabsight.figure import Figure
from tabsight.formats import choose_decimals, format_date, format_number, js_spec, locale_payload
from tabsight.i18n import text
from tabsight.io import as_frame
from tabsight.profile import Profile, _prepare, profile
from tabsight.settings import Settings, resolve
from tabsight.spec import ChartSpec
from tabsight.theme import Theme, get_theme
from tabsight.warnings import DataWarning, InvalidSpecError, safe_repr, warn

__all__ = ["DRAWN_KINDS", "chart"]

BAR_KINDS = ("bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar")
LINE_KINDS = ("line", "multi_line", "area", "stacked_area", "sparkline")
MAP_KINDS = ("choropleth", "symbol_map", "density_map", "flow_map")
RELATION_KINDS = ("scatter", "bubble", "histogram", "boxplot")
PART_KINDS = ("treemap", "sunburst", "waterfall", "funnel", "pareto")
EXTRA_KINDS = ("bullet", "gauge", "combo")
GRID_KINDS = ("heatmap", "calendar_heatmap", "sankey")
DRAWN_KINDS = (*BAR_KINDS, *LINE_KINDS, "donut", "kpi", "table", *MAP_KINDS, *RELATION_KINDS, *PART_KINDS,
               *EXTRA_KINDS, "lollipop", *GRID_KINDS)  # fmt: skip
MAX_TABLE_ROWS = 500
MAX_DONUT_SLICES = 8
HBAR_LABEL_CHARS = 16
HBAR_CATEGORIES = 15


def chart(
    data: Any,
    kind: str = "bar",
    *,
    x: str | Sequence[str] | None = None,
    y: str | Sequence[str] | None = None,
    color: str | None = None,
    agg: str | None = None,
    sort: str | Sequence[str] | None = None,
    top: int | None = None,
    freq: str | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    unit: str | None = None,
    currency: str | None = None,
    decimals: int | None = None,
    format: str | None = None,
    theme: str | Theme | None = None,
    locale: str | None = None,
    palette: str | None = None,
    colors: Mapping[str, str] | None = None,
    height: int | None = None,
    prof: Profile | None = None,
    geo: str | None = None,
    lat: str | None = None,
    lon: str | None = None,
    map: str | None = None,
    level: str | None = None,
    layer: str | None = None,
    geo_map: Mapping[str, str] | None = None,
    geo_names: str | None = None,
    projection: str | None = None,
    size: str | None = None,
    goal: float | str | None = None,
    bins: int | None = None,
    bin_width: float | None = None,
    source: str | None = None,
    target: str | None = None,
    facet: str | None = None,
    trend: bool | None = None,
    forecast: int | None = None,
    season: int | None = None,
    ref: str | float | Sequence[str | float] | None = None,
    band: Sequence[str | float] | None = None,
    outliers: bool | None = None,
    insights: bool | None = None,
    compare: str | None = None,
    as_of: str | None = None,
) -> Figure:
    """Build a chart. ``x`` is what you group by, ``y`` the measure(s), ``color`` splits
    the series. Everything else has a sensible default and can be overridden.

    ``kind="auto"`` draws the best chart ``ts.recommend`` finds for these fields.

    Maps (``kind="map"``, ``"choropleth"`` or ``"symbol_map"``): ``geo`` is the column of
    places, matched automatically to countries, regions or cities. ``map`` picks the map
    (``"world"`` or a country such as ``"Ireland"``), ``level`` (country, region, city)
    and ``layer`` (for example ``"nation"`` for the UK) narrow it, ``geo_map`` fixes
    spellings, ``geo_names`` sets the language of place names, and ``lat``/``lon`` place
    points by coordinates.

    Analytics: ``trend=True`` adds a least-squares trend line, ``forecast=6`` estimates
    the next 6 periods (Holt-Winters, dashed, with a rough range; ``season=`` overrides
    the season length), ``ref="mean"`` (``"median"``, ``"p90"``, a number, or a list)
    draws reference lines, ``band=("p25", "p75")`` shades a band, ``outliers=True``
    circles unusual points, and ``insights=True`` adds plain-English facts under the
    chart. A KPI takes ``compare="previous_year"`` (or ``"previous_quarter"``,
    ``"previous_month"``) and ``as_of="2017-12-31"``; "today" is otherwise the latest
    date in the data."""
    if facet is not None:
        if any(v for v in (trend, forecast, ref, band, outliers, insights, compare)):
            raise InvalidSpecError(
                "trend, forecast, reference lines, outliers, insights and comparisons aren't drawn in "
                "small multiples yet; draw one chart per value instead"
            )
        args = {
            k: v
            for k, v in locals().items()
            if k not in ("data", "kind", "facet") and v is not None
        }
        from tabsight.charts.facets import facet_chart

        return facet_chart(_prepare(as_frame(data))[0], kind, facet, args, chart)
    settings = resolve(locale=locale, currency=currency, palette=palette)
    chosen: list[str] = []
    freq_source = "asked" if freq else None
    if kind == "auto":
        from tabsight.recommend import recommend

        data, _ = _prepare(as_frame(data))
        prof = prof if prof is not None else profile(data, quiet=True)
        recs = recommend(data, x=x, y=y, color=color, prof=prof)
        pick = recs.best
        kind, x, color = pick.kind, pick.spec.x, pick.spec.color
        y, size = pick.spec.y, size or pick.spec.size
        geo = geo or pick.spec.geo
        top = top if top is not None else pick.spec.top
        sort = sort if sort is not None else pick.spec.sort
        runner_up = next((r for r in recs if r.available and r.kind != pick.kind), None)
        chosen.append(
            f"{pick.kind.replace('_', ' ')} chosen automatically (score {pick.score}): {pick.reason}"
            + (
                f"; next best: {runner_up.kind.replace('_', ' ')} ({runner_up.score})"
                if runner_up
                else ""
            )
        )
        if freq is None and pick.spec.options.get("freq"):
            freq, freq_source = pick.spec.options["freq"], "auto"
    theme_obj = theme if isinstance(theme, Theme) else get_theme(theme or settings.theme)
    options: dict[str, Any] = {"freq": freq} if freq else {}
    for key, value in (("map", map), ("level", level), ("layer", layer), ("geo_map", geo_map),
                       ("geo_names", geo_names), ("projection", projection), ("goal", goal),
                       ("bins", bins), ("bin_width", bin_width), ("trend", trend), ("forecast", forecast),
                       ("season", season), ("ref", ref), ("band", band), ("outliers", outliers),
                       ("insights", insights), ("compare", compare), ("as_of", as_of)):  # fmt: skip
        if value is not None:
            options[key] = dict(value) if isinstance(value, Mapping) else value
    spec = ChartSpec(
        kind, x=_as_tuple(x), y=_as_tuple(y), color=color, agg=agg, sort=_as_tuple(sort), top=top, unit=unit, currency=currency,
        decimals=decimals, format=format, title=title, subtitle=subtitle, options=options, geo=geo, lat=lat, lon=lon, size=size, source=source, target=target, facet=facet,
    )  # fmt: skip
    if height is not None and (type(height) is not int or not 80 <= height <= 4000):
        raise InvalidSpecError("height must be a whole number of pixels from 80 to 4000")

    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    ctx = _Context(spec, prof, settings, theme_obj, ColorRegistry(settings.palette, pinned=colors))
    ctx.decisions.extend(chosen or [f"{spec.kind.replace('_', ' ')} chart, as asked"])
    ctx.freq_source = freq_source

    from tabsight.charts import pane

    if pane.asked(ctx):
        pane.check_kind(ctx, spec.kind)
    if spec.options.get("compare") and spec.kind != "kpi":
        raise InvalidSpecError("compare= works on KPI cards; for charts, use ts.compare(...)")
    fig = _draw(frame, ctx, height)
    if spec.options.get("insights"):
        fig = _with_insights(fig, frame, ctx)
    return fig


def _draw(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    spec = ctx.spec
    if spec.kind in MAP_KINDS:
        from tabsight.charts.maps import map_chart

        return map_chart(frame, ctx, height)
    if spec.kind in RELATION_KINDS:
        from tabsight.charts import relation

        build = {"scatter": relation.scatter, "bubble": relation.scatter,
                 "histogram": relation.histogram, "boxplot": relation.boxplot}[spec.kind]  # fmt: skip
        return build(frame, ctx, height)
    if spec.kind in PART_KINDS:
        from tabsight.charts import parts

        build = {"treemap": parts.tree, "sunburst": parts.tree, "waterfall": parts.waterfall,
                 "funnel": parts.funnel, "pareto": parts.pareto}[spec.kind]  # fmt: skip
        return build(frame, ctx, height)
    if spec.kind in EXTRA_KINDS:
        from tabsight.charts import extra

        build = {"bullet": extra.bullet, "gauge": extra.gauge, "combo": extra.combo}[spec.kind]
        return build(frame, ctx, height)
    if spec.kind in GRID_KINDS:
        from tabsight.charts import grids

        build = {"heatmap": grids.heatmap, "calendar_heatmap": grids.calendar_heatmap,
                 "sankey": grids.sankey}[spec.kind]  # fmt: skip
        return build(frame, ctx, height)
    if spec.kind == "kpi":
        return _kpi(frame, ctx, height)
    if spec.kind == "table":
        return _table(frame, ctx, height)
    return _echarts(frame, ctx, height)


def _with_insights(fig: Figure, frame: pd.DataFrame, ctx: _Context) -> Figure:
    """Plain-English facts about exactly the fields this chart shows."""
    import dataclasses

    from tabsight.insight import insights

    ys = [m["column"] for m in ctx.facts.get("measures", []) if m["column"] in ctx.prof]
    if not ys:
        return fig
    dims = ctx.dims() if ctx.spec.x is not None else []
    xs = [
        d
        for d in [*dims, *([ctx.spec.color] if ctx.spec.color else [])]
        if ctx.prof[d].role != "time"
    ]
    date = next((d for d in dims if ctx.prof[d].role == "time"), None)
    found = insights(frame, y=ys, x=xs or None, date=date, as_of=ctx.spec.options.get("as_of"),
                     max_items=4, locale=ctx.locale, prof=ctx.prof) if (xs or date) else None  # fmt: skip
    items = tuple(i.to_dict() for i in found) if found else ()
    decision = (f"{len(items)} insight(s) found by fixed rules (facts, never causes), {items[0]['scope']}"
                if items else "no insight rule found anything worth saying for these fields")  # fmt: skip
    return dataclasses.replace(
        fig, insights=items, decisions=(*fig.decisions, decision.rstrip(", "))
    )


def _as_tuple(value: Any) -> Any:
    return tuple(value) if isinstance(value, list | tuple) else value


# ---------------------------------------------------------------- shared context


class _Context:
    def __init__(
        self,
        spec: ChartSpec,
        prof: Profile,
        settings: Settings,
        theme: Theme,
        colors: ColorRegistry,
    ):
        self.spec = spec
        self.prof = prof
        self.settings = settings
        self.theme = theme
        self.colors = colors
        self.notes: list[str] = []
        self.decisions: list[str] = []
        self.facts: dict[str, Any] = {}
        self.freq_source: str | None = None

    @property
    def locale(self) -> str:
        return self.settings.locale

    def measures(self) -> list[Measure]:
        ys = self.spec.y
        if ys is None:
            raise InvalidSpecError(f"a {self.spec.kind} chart needs y=<measure column>")
        names = [ys] if isinstance(ys, str) else list(ys)
        out = []
        for name in names:
            if name not in self.prof:
                raise _missing(name, self.prof)
            field = self.prof[name]
            agg = self.spec.agg or (field.agg if field.agg not in ("none", "wavg") else "count")
            if field.role in ("dimension", "text", "time") and agg not in ("count", "countd"):
                agg = "countd"
                self.notes.append(f"{name} is not a number, so it is counted (distinct values)")
                why = "it is not a number"
            elif self.spec.agg:
                why = "as asked"
            else:
                # "averaged, because ..." would repeat the verb: keep only the reason
                why = "; ".join(r.split(", because ", 1)[-1] if r.startswith(_AGG_WORDS.get(agg, "~")) else r
                                for r in field.reasons) or "the default for this column"  # fmt: skip
            self.decisions.append(f"{name} is {_AGG_WORDS.get(agg, agg)}: {why}")
            out.append(Measure(name, agg))
            fmt = self.number_kwargs(out[-1])
            unit = fmt.pop("unit")
            fact = {"column": name, "agg": agg, "unit": field.unit, "role": field.role, "default_agg": field.agg,
                    "full": js_spec(unit, "full", **fmt), "compact": js_spec(unit, "compact", **fmt)}  # fmt: skip
            known = self.facts.setdefault("measures", [])
            if not any(
                f["column"] == name and f["agg"] == agg for f in known
            ):  # a builder may ask twice
                known.append(fact)
        return out

    def describe_format(self, measures: list[Measure], where: str) -> None:
        for m in measures:
            kw = self.number_kwargs(m)
            unit = kw["unit"]
            how = f"{unit} in {kw['currency']}" if unit == "currency" else unit
            pattern = f" with the pattern {kw['pattern']!r}" if "pattern" in kw else ""
            self.decisions.append(
                f"{m.label} is formatted as {how} for {self.locale}{pattern}{where}"
            )

    def dims(self) -> list[str]:
        xs = self.spec.x
        names = [] if xs is None else ([xs] if isinstance(xs, str) else list(xs))
        for name in names + ([self.spec.color] if self.spec.color else []):
            if name not in self.prof:
                raise _missing(name, self.prof)
        return names

    def number_kwargs(self, m: Measure) -> dict[str, Any]:
        """format_number / js_spec keyword arguments for a measure."""
        field = self.prof[m.column] if m.column is not None and m.column in self.prof else None
        if m.agg in ("count", "countd"):
            unit = self.spec.unit or "count"
        else:
            unit = self.spec.unit or (
                field.unit if field is not None and field.unit != "none" else "number"
            )
        kwargs: dict[str, Any] = {"locale": self.locale, "decimals": self.spec.decimals}
        if unit == "currency":
            kwargs["currency"] = (
                self.spec.currency or (field.currency if field else None) or self.settings.currency
            )
        if unit in ("percent", "pp") and field is not None and field.percent_scale:
            kwargs["percent_scale"] = field.percent_scale
        if unit == "duration" and field is not None and field.duration_unit:
            kwargs["duration_unit"] = field.duration_unit
        if self.spec.format is not None:
            kwargs["pattern"] = self.spec.format
        return {"unit": unit, **kwargs}

    def js(self, m: Measure, style: str) -> dict[str, Any]:
        kw = self.number_kwargs(m)
        unit = kw.pop("unit")
        return js_spec(unit, style, **kw)

    def fmt(self, value: Any, m: Measure, style: str) -> str:
        kw = self.number_kwargs(m)
        unit = kw.pop("unit")
        return format_number(value, unit, style, **kw)

    def measure_title(self, m: Measure) -> str:
        key = {"sum": "sum_of", "mean": "avg_of", "count": "count_of", "countd": "distinct_of"}.get(
            m.agg
        )
        if key is None:
            return f"{m.agg.capitalize()} {m.label}"
        return text(key, field=m.label)

    def title(self, measures: list[Measure], dims: list[str]) -> str:
        if self.spec.title:
            return self.spec.title
        if len(measures) == 1:
            what = _pretty(self.measure_title(measures[0]))
        else:
            what = _join([_pretty(m.label) for m in measures])
        if not dims:
            return what
        return text("by", measure=what, dimension=_join([_pretty(d) for d in dims]))


_AGG_WORDS = {
    "sum": "summed", "mean": "averaged", "median": "summarised by its median", "min": "summarised by its minimum",
    "max": "summarised by its maximum", "count": "counted", "countd": "counted (distinct values)",
    "wavg": "a weighted average",
}  # fmt: skip


def _pane_asked(ctx: _Context) -> bool:
    from tabsight.charts import pane

    return pane.asked(ctx)


def _same_parents(frame: pd.DataFrame, parents: list[str], i: int) -> bool:
    return all(frame[p].iloc[i] == frame[p].iloc[i - 1] for p in parents)


def _table_sort(ctx: _Context, d: str, has_measures: bool) -> Any:
    """Without a measure there is nothing to rank by, so rows keep their natural order."""
    if has_measures or ctx.spec.sort is not None or ctx.prof[d].ordered:
        return ctx.spec.sort
    return "none"


def _order_words(sort: Any, ordered: bool) -> str:
    if isinstance(sort, tuple):
        return "in the order you gave"
    if sort == "none":
        return "in natural order (A to Z, 2 before 10)"
    if sort is None and ordered:
        return "in its own order (like Low, Medium, High)"
    if sort == "asc":
        return "sorted smallest first, as asked"
    return "sorted largest first, so the ranking reads at a glance"


def _colors_pinned(ctx: _Context) -> bool:
    return bool(ctx.colors.to_dict().get("pinned"))


def _pretty(name: str) -> str:
    """Column names read better in titles without underscores: Sub_Category -> Sub Category."""
    return name.replace("_", " ")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _missing(name: str, prof: Profile) -> InvalidSpecError:
    import difflib

    hint = difflib.get_close_matches(name, prof.names(), n=1)
    return InvalidSpecError(
        f"column {safe_repr(name)} not found"
        + (f"; did you mean {safe_repr(hint[0])}?" if hint else "")
    )


def _labels(values: pd.Series, grain: str | None, ctx: _Context, compact: bool) -> list[str]:
    if pd.api.types.is_datetime64_any_dtype(values):
        style = "compact" if compact and grain in ("month", "day") else "full"
        return [format_date(v, grain or "day", style, locale=ctx.locale) for v in values]
    return [
        text("unknown") if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
        for v in values
    ]


# ---------------------------------------------------------------- ECharts kinds


def _echarts(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    spec = ctx.spec
    kind = spec.kind
    measures = ctx.measures()
    dims = ctx.dims()
    if not dims:
        raise InvalidSpecError(f"a {kind} chart needs x=<column to group by>")
    if len(dims) > 1:
        raise InvalidSpecError(f"a {kind} chart takes one x column; use color= for a second one")
    x = dims[0]
    color = spec.color
    if kind in LINE_KINDS and kind != "sparkline":
        from tabsight.charts import relation

        if relation.is_numeric(ctx, frame, x):
            return relation.numeric_lines(frame, ctx, height, x)
    if (
        kind in ("multi_line", "stacked_area", "stacked_bar", "stacked100_bar", "grouped_bar")
        and not color
        and len(measures) == 1
    ):
        raise InvalidSpecError(f"a {kind} chart needs color=<column> to split the series")
    if kind == "donut" and (color or len(measures) > 1):
        raise InvalidSpecError("a donut shows one measure split by one column")

    group = [x] + ([color] if color else [])
    top = spec.top
    if kind == "donut" and top is None:
        top = MAX_DONUT_SLICES - 1
    result = aggregate(
        frame, group, measures, freq=spec.options.get("freq"), top=top, sort=spec.sort,
        missing="zero" if kind in BAR_KINDS else None, prof=ctx.prof,
    )  # fmt: skip
    ctx.notes.extend(result.notes)
    cut = next((d for d in group if d in result.categories), None)
    if cut is not None and result.other:
        ctx.notes.append(text("top_n_of", n=top, total=result.categories[cut]))
        why = (
            ", because a donut with more slices can't be read"
            if kind == "donut" and spec.top is None
            else ""
        )
        ctx.decisions.append(
            f"only the top {top} {cut} values are drawn; the rest are grouped as Other, in grey{why}"
        )
    grain = spec.options.get("freq") or ctx.prof[x].grain
    x_time = ctx.prof[x].role == "time"
    if x_time:
        source = {"asked": "as asked", "auto": "to suit the time span"}.get(
            ctx.freq_source or "", "the grain of the dates"
        )
        ctx.decisions.append(f"{x} is grouped by {grain} ({source}) and shown in time order")
    else:
        ctx.decisions.append(f"{x} is {_order_words(spec.sort, bool(ctx.prof[x].ordered))}")

    values = result.frame.copy()
    if not pd.api.types.is_datetime64_any_dtype(values[x]):
        values[x] = values[x].astype("object").where(values[x].notna(), text("unknown"))
    x_values = list(dict.fromkeys(values[x].tolist()))
    labels = _labels(pd.Series(x_values), grain, ctx, compact=len(x_values) > 8)
    other_x = set(values.loc[values[OTHER_FLAG].eq(True), x]) if OTHER_FLAG in values else set()

    if kind == "donut":
        option, kind = _build.donut(values, x, labels, measures[0], other_x, ctx)
        if kind != "donut":
            ctx.notes.append("negative values cannot be shown as slices, so this is drawn as bars")
            ctx.decisions.append(
                "drawn as horizontal bars, because negative values can't be slices"
            )
    elif kind in BAR_KINDS or kind == "lollipop":
        lollipop = kind == "lollipop"
        if lollipop:
            if color or len(measures) > 1:
                raise InvalidSpecError("a lollipop shows one measure by one column")
            kind = "bar"
        if (
            kind == "bar"
            and not x_time
            and (
                max((len(lb) for lb in labels), default=0) > HBAR_LABEL_CHARS
                or len(labels) > HBAR_CATEGORIES
            )
        ):  # dates always read left to right
            kind = "hbar"
            ctx.notes.append("drawn as horizontal bars so every label can be read")
            ctx.decisions.append(
                f"switched to horizontal bars: {len(labels)} categories or labels longer than "
                f"{HBAR_LABEL_CHARS} characters would not fit side by side"
            )
        option = _build.bars(values, x, x_values, labels, measures, color, kind, other_x, ctx)
        if lollipop:
            from tabsight.charts.extra import lollipop_from_bars

            option = lollipop_from_bars(option, kind == "hbar", ctx)
            kind = "lollipop"
        ctx.decisions.append("the value axis starts at zero, so bar lengths are honest")
        if color:
            ctx.decisions.append("a missing combination is shown as 0")
    else:
        option = _build.lines(values, x, x_values, labels, measures, color, kind, ctx)
        ctx.decisions.append("lines are straight between real data points, never smoothed")
        ctx.decisions.append(
            {"gap": "a missing period is left as a gap", "zero": "a missing period is drawn as 0",
             "connect": "a missing period is bridged by the line"}[ctx.settings.missing]
        )  # fmt: skip
    if pane_asked := _pane_asked(ctx):
        from tabsight.charts import pane

        pane.apply_category(option, ctx, kind=kind, x_values=x_values, grain=grain if x_time else None,
                            x_time=x_time, partial=result.partial_period)  # fmt: skip
    if color:
        pinned = " (with your pinned colours)" if _colors_pinned(ctx) else ""
        ctx.decisions.append(
            f"{color} values take colours from the {ctx.settings.palette} palette in sorted order, "
            f"so each value keeps its colour in every chart{pinned}"
        )
    ctx.describe_format(measures, "; short on the axis, in full in tooltips")
    numbers = pd.concat([pd.to_numeric(values[m.label], errors="coerce") for m in measures])
    ctx.facts.update(
        x_time=x_time, x_ordered=bool(ctx.prof[x].ordered) or isinstance(spec.sort, tuple),
        categories=len(x_values), longest_label=max((len(lb) for lb in labels), default=0),
        series=int(values[color].nunique(dropna=False)) if color else len(measures),
        negative=bool((numbers < 0).any()), partial_period=result.partial_period,
        one_segment=bool(color) and int(values.groupby(x, dropna=False, observed=True)[str(color)].nunique().max() or 0) <= 1,
        rows=int(numbers.notna().sum()),
    )  # fmt: skip

    if color:
        n_colors = values[color].nunique()
        if n_colors > 10:
            warn(
                f"{n_colors} colours in one chart are hard to tell apart; consider fewer values",
                DataWarning,
            )
    fig_height = height or _build.default_height(kind, len(labels))
    if pane_asked and ctx.facts.get("forecast"):
        ctx.facts["categories"] = len(option["xAxis"]["data"])
    return Figure(
        kind=kind,
        spec=spec,
        title=ctx.title(measures, dims),
        subtitle=spec.subtitle,
        option=option,
        locales=locale_payload([ctx.locale]),
        theme=ctx.theme,
        height=fig_height,
        notes=tuple(dict.fromkeys(ctx.notes)),
        decisions=tuple(dict.fromkeys(ctx.decisions)),
        facts=ctx.facts,
    )


# ---------------------------------------------------------------- KPI and table


def _kpi(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    measures = ctx.measures()
    if len(measures) != 1:
        raise InvalidSpecError("a KPI shows exactly one measure")
    if ctx.spec.x is not None:
        raise InvalidSpecError("a KPI shows one number; leave x= out")
    m = measures[0]
    label = ctx.spec.title or _pretty(ctx.measure_title(m))
    ctx.describe_format(measures, "; short on the card, in full on hover")
    if ctx.spec.options.get("compare"):
        kpi = _kpi_compare(frame, ctx, m)
    else:
        result = aggregate(frame, None, measures, prof=ctx.prof)
        value = result.values[m.label].iloc[0] if len(result.frame) else None
        kpi = {
            "label": None,  # the tile title already names the measure
            "value_text": ctx.fmt(value, m, "compact") or text("no_data"),
            "value_full": ctx.fmt(value, m, "full"),
            "detail": ctx.spec.subtitle,
        }
    return Figure(
        kind="kpi", spec=ctx.spec, title=label, kpi=kpi, locales=locale_payload([ctx.locale]),
        theme=ctx.theme, height=height or 120, notes=tuple(ctx.notes), decisions=tuple(ctx.decisions),
        facts=ctx.facts,
    )  # fmt: skip


def _kpi_compare(frame: pd.DataFrame, ctx: _Context, m: Measure) -> dict[str, Any]:
    """The current period's value, and its change on the same window one period earlier."""
    from tabsight.periods import compare

    date = next((f.name for f in ctx.prof.fields if f.role == "time"), None)
    if date is None:
        raise InvalidSpecError("compare= needs a date column to tell the periods apart")
    how = ctx.spec.options["compare"]
    c = compare(frame, m.column or date, date, compare=how, as_of=ctx.spec.options.get("as_of"), agg=m.agg,
                locale=ctx.locale, prof=ctx.prof)  # fmt: skip
    unit = ctx.number_kwargs(m)["unit"]
    if c.change is None:
        change = c.note or text("no_previous_period")
    else:
        arrow = "▲" if c.change > 0 else ("▼" if c.change < 0 else "■")
        if unit in ("percent", "pp"):
            size = format_number(abs(c.change), "pp", "full", locale=ctx.locale, decimals=1,
                                 percent_scale=ctx.number_kwargs(m).get("percent_scale", "fraction"))  # fmt: skip
        elif c.pct is not None:
            size = format_number(abs(c.pct), "percent", "full", locale=ctx.locale, decimals=1)
        else:
            size = ctx.fmt(abs(c.change), m, "compact")
        change = f"{arrow} {size.lstrip('+')} vs {c.previous_label}"
    ctx.decisions.append(
        f"the card shows {c.current_label} and compares it with {c.previous_label}: the same window one "
        f"{'period' if how == 'previous_period' else how.split('_')[1]} earlier, so a period that isn't over "
        f"is never set against a whole one"
    )
    ctx.decisions.append(
        f"'today' is {c.as_of.date()}: {c.as_of_source}; as_of= changes it, and the computer's clock is never used"
    )
    ctx.facts.update(compare=how, as_of=str(c.as_of.date()))
    detail = f"{c.current_label} · {change}"
    return {
        "label": None,
        "value_text": ctx.fmt(c.current, m, "compact") or text("no_data"),
        "value_full": f"{ctx.fmt(c.current, m, 'full')} in {c.current_label} (data up to {c.as_of.date()})",
        "detail": f"{ctx.spec.subtitle} · {detail}" if ctx.spec.subtitle else detail,
    }


def _table(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    dims = ctx.dims()
    measures = ctx.measures() if ctx.spec.y is not None else []
    if not dims and not measures:
        raise InvalidSpecError("a table needs x=<columns> and/or y=<measures>")
    result: Aggregation = aggregate(
        frame, dims or None, measures, freq=ctx.spec.options.get("freq"), top=ctx.spec.top,
        sort=ctx.spec.sort, missing="connect", prof=ctx.prof,
    )  # fmt: skip
    ctx.notes.extend(result.notes)
    vals = result.values
    total_rows = len(vals)
    shown = vals.head(MAX_TABLE_ROWS)
    columns = [{"name": _pretty(d), "align": "left"} for d in dims] + [
        {"name": _pretty(ctx.measure_title(m)), "align": "right"} for m in measures
    ]
    cells: list[list[str]] = [[] for _ in range(len(shown))]
    for level, d in enumerate(dims):
        grain = ctx.spec.options.get("freq") or ctx.prof[d].grain
        labels = _labels(shown[d], grain, ctx, compact=False)
        for i, label in enumerate(labels):
            # Like a BI table: a parent value is shown once, not repeated on every row.
            repeated = (
                level < len(dims) - 1
                and i > 0
                and all(cells[i][j] == "" or cells[i][j] == cells[i - 1][j] for j in range(level))
                and labels[i - 1] == label
                and _same_parents(shown, dims[:level], i)
            )
            cells[i].append("" if repeated else label)
    for m in measures:
        decimals = ctx.spec.decimals
        kw = ctx.number_kwargs(m)
        unit = kw.pop("unit")
        if decimals is None and "pattern" not in kw:
            if unit in ("currency", "number", "count"):
                kw["decimals"] = choose_decimals(shown[m.label], unit)
            elif unit in ("percent", "pp"):
                kw["decimals"] = 1  # one setting per column, so the numbers line up
        for i, v in enumerate(shown[m.label]):
            cells[i].append(format_number(v, unit, "full", **kw))
        ctx.facts.setdefault("column_formats", []).append(
            js_spec(unit, "full", **kw)
        )  # for dashboards
    if dims:
        ctx.decisions.append(
            "a parent value is shown once rather than repeated on every row" if len(dims) > 1
            else f"{dims[0]} is {_order_words(_table_sort(ctx, dims[0], bool(measures)), bool(ctx.prof[dims[0]].ordered))}"
        )  # fmt: skip
    ctx.describe_format(measures, "; one number of decimals per column so the digits line up")
    ctx.facts.update(rows_total=total_rows, rows_shown=len(shown))
    note = None
    if total_rows > MAX_TABLE_ROWS:
        note = f"showing the first {MAX_TABLE_ROWS:,} of {total_rows:,} rows"
    return Figure(
        kind="table", spec=ctx.spec, title=ctx.title(measures, dims) if measures else ", ".join(dims),
        subtitle=ctx.spec.subtitle, table={"columns": columns, "rows": cells, "note": note},
        locales=locale_payload([ctx.locale]), theme=ctx.theme, height=height or 400, notes=tuple(ctx.notes),
        decisions=tuple(ctx.decisions), facts=ctx.facts,
    )  # fmt: skip
