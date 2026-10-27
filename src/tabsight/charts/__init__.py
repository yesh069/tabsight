"""``ts.chart``: from a DataFrame to a finished, BI-quality chart.

Phase 3 draws bar, line, area, donut, KPI and table charts. The rest of the 33 kinds in
``tabsight.spec.CHART_KINDS`` raise a clear "arrives in phase N" error until they land.
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
DRAWN_KINDS = (*BAR_KINDS, *LINE_KINDS, "donut", "kpi", "table")
_LATER = {
    "choropleth": 5, "symbol_map": 5, "density_map": 6, "flow_map": 6, "treemap": 6, "sunburst": 6,
    "waterfall": 6, "funnel": 6, "combo": 6, "calendar_heatmap": 6, "sankey": 6, "scatter": 6,
    "bubble": 6, "heatmap": 6, "histogram": 6, "boxplot": 6, "gauge": 6, "pareto": 6,
    "lollipop": 6, "bullet": 6,
}  # fmt: skip
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
) -> Figure:
    """Build a chart. ``x`` is what you group by, ``y`` the measure(s), ``color`` splits
    the series. Everything else has a sensible default and can be overridden."""
    settings = resolve(locale=locale, currency=currency, palette=palette)
    theme_obj = theme if isinstance(theme, Theme) else get_theme(theme or settings.theme)
    options: dict[str, Any] = {"freq": freq} if freq else {}
    spec = ChartSpec(
        kind, x=_as_tuple(x), y=_as_tuple(y), color=color, agg=agg, sort=_as_tuple(sort), top=top, unit=unit, currency=currency,
        decimals=decimals, format=format, title=title, subtitle=subtitle, options=options,
    )  # fmt: skip
    if spec.kind in _LATER:
        raise InvalidSpecError(
            f"{spec.kind} charts arrive in phase {_LATER[spec.kind]}; see the roadmap"
        )
    if height is not None and (type(height) is not int or not 80 <= height <= 4000):
        raise InvalidSpecError("height must be a whole number of pixels from 80 to 4000")

    frame, _ = _prepare(as_frame(data))
    prof = prof if prof is not None else profile(frame, quiet=True)
    ctx = _Context(spec, prof, settings, theme_obj, ColorRegistry(settings.palette, pinned=colors))

    if spec.kind == "kpi":
        return _kpi(frame, ctx, height)
    if spec.kind == "table":
        return _table(frame, ctx, height)
    return _echarts(frame, ctx, height)


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
            out.append(Measure(name, agg))
        return out

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


def _same_parents(frame: pd.DataFrame, parents: list[str], i: int) -> bool:
    return all(frame[p].iloc[i] == frame[p].iloc[i - 1] for p in parents)


def _pretty(name: str) -> str:
    """Column names read better in titles without underscores: Sub_Category -> Sub Category."""
    return name.replace("_", " ")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _missing(name: str, prof: Profile) -> InvalidSpecError:
    import difflib

    hint = difflib.get_close_matches(name, prof.names(), n=1)
    return InvalidSpecError(
        f"column {safe_repr(name)} not found" + (f"; did you mean {hint[0]!r}?" if hint else "")
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
    if x in result.categories and result.other:
        ctx.notes.append(text("top_n_of", n=top, total=result.categories[x]))
    grain = spec.options.get("freq") or ctx.prof[x].grain

    values = result.frame.copy()
    if not pd.api.types.is_datetime64_any_dtype(values[x]):
        values[x] = values[x].astype("object").where(values[x].notna(), text("unknown"))
    x_values = list(dict.fromkeys(values[x].tolist()))
    labels = _labels(pd.Series(x_values), grain, ctx, compact=len(x_values) > 8)
    other_x = (
        set(values.loc[values[OTHER_FLAG].fillna(False).astype(bool), x])
        if OTHER_FLAG in values
        else set()
    )

    if kind == "donut":
        option, kind = _build.donut(values, x, labels, measures[0], other_x, ctx)
        if kind != "donut":
            ctx.notes.append("negative values cannot be shown as slices, so this is drawn as bars")
    elif kind in BAR_KINDS:
        if kind == "bar" and (
            max((len(lb) for lb in labels), default=0) > HBAR_LABEL_CHARS
            or len(labels) > HBAR_CATEGORIES
        ):
            kind = "hbar"
            ctx.notes.append("drawn as horizontal bars so every label can be read")
        option = _build.bars(values, x, x_values, labels, measures, color, kind, other_x, ctx)
    else:
        option = _build.lines(values, x, x_values, labels, measures, color, kind, ctx)

    if color:
        n_colors = values[color].nunique()
        if n_colors > 10:
            warn(
                f"{n_colors} colours in one chart are hard to tell apart; consider fewer values",
                DataWarning,
            )
    fig_height = height or _build.default_height(kind, len(labels))
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
    )


# ---------------------------------------------------------------- KPI and table


def _kpi(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    measures = ctx.measures()
    if len(measures) != 1:
        raise InvalidSpecError("a KPI shows exactly one measure")
    if ctx.spec.x is not None:
        raise InvalidSpecError("a KPI shows one number; leave x= out")
    m = measures[0]
    result = aggregate(frame, None, measures, prof=ctx.prof)
    value = result.values[m.label].iloc[0] if len(result.frame) else None
    label = ctx.spec.title or _pretty(ctx.measure_title(m))
    kpi = {
        "label": None,  # the tile title already names the measure
        "value_text": ctx.fmt(value, m, "compact") or text("no_data"),
        "value_full": ctx.fmt(value, m, "full"),
        "detail": ctx.spec.subtitle,
    }
    return Figure(
        kind="kpi", spec=ctx.spec, title=label, kpi=kpi, locales=locale_payload([ctx.locale]),
        theme=ctx.theme, height=height or 120, notes=tuple(ctx.notes),
    )  # fmt: skip


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
    note = None
    if total_rows > MAX_TABLE_ROWS:
        note = f"showing the first {MAX_TABLE_ROWS:,} of {total_rows:,} rows"
    return Figure(
        kind="table", spec=ctx.spec, title=ctx.title(measures, dims) if measures else ", ".join(dims),
        subtitle=ctx.spec.subtitle, table={"columns": columns, "rows": cells, "note": note},
        locales=locale_payload([ctx.locale]), theme=ctx.theme, height=height or 400, notes=tuple(ctx.notes),
    )  # fmt: skip
