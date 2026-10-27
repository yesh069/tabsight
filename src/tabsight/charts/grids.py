"""Grids and flows: heatmap, calendar heatmap and Sankey."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import aggregate
from tabsight.charts import _build
from tabsight.charts._common import figure, item_tooltip, num, scale, visual_map
from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError

if TYPE_CHECKING:
    from tabsight.charts import _Context

__all__ = ["calendar_heatmap", "heatmap", "sankey"]

MAX_CELLS_LABELLED = 150
MAX_LINKS = 60
MAX_YEARS = 3


def heatmap(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    """Columns from x, rows from color, colour from the measure."""
    dims = ctx.dims()
    rows_col = ctx.spec.color
    if len(dims) != 1 or rows_col is None:
        raise InvalidSpecError("a heatmap needs x=<columns> and color=<rows> (and y=<measure>)")
    x = dims[0]
    measures = ctx.measures()
    if len(measures) != 1:
        raise InvalidSpecError("a heatmap shows one measure")
    m = measures[0]
    result = aggregate(frame, [x, rows_col], [m], freq=ctx.spec.options.get("freq"), sort=ctx.spec.sort,
                       prof=ctx.prof, missing="connect")  # fmt: skip
    ctx.notes.extend(result.notes)
    vals = result.values
    from tabsight.charts import _labels

    x_values = list(dict.fromkeys(vals[x].tolist()))
    row_values = list(dict.fromkeys(vals[rows_col].tolist()))
    x_labels = _labels(pd.Series(x_values), ctx.spec.options.get("freq") or ctx.prof[x].grain, ctx,
                       compact=len(x_values) > 8)  # fmt: skip
    row_labels = _labels(pd.Series(row_values), ctx.prof[rows_col].grain, ctx, compact=False)
    xi = {v: i for i, v in enumerate(x_values)}
    yi = {v: i for i, v in enumerate(row_values)}
    data: list[dict[str, Any]] = []
    for _, r in vals.iterrows():
        v = num(r[m.label])
        i, j = xi[r[x]], yi[r[rows_col]]
        data.append({"value": [i, j, v], "name": f"{row_labels[j]} · {x_labels[i]}"})
    lo, hi, ramp, diverging = scale((d["value"][2] for d in data), ctx)
    option = _build._base(ctx)
    option["xAxis"] = {
        **_build._category_axis(x_labels, ctx, horizontal=False, gap=True),
        "splitArea": {"show": False},
    }
    option["yAxis"] = {
        **_build._category_axis(row_labels, ctx, horizontal=True, gap=True),
        "inverse": True,
    }
    show_labels = len(data) <= MAX_CELLS_LABELLED
    option["series"] = [{"type": "heatmap", "name": ctx.measure_title(m), "data": data,
                         "label": {"show": show_labels, "fontSize": 10, "formatter": {"$label": ctx.js(m, "compact")}},
                         "itemStyle": {"borderColor": ctx.theme.tile, "borderWidth": 1},
                         "emphasis": {"itemStyle": {"borderColor": ctx.theme.text, "borderWidth": 1}}}]  # fmt: skip
    option["visualMap"] = visual_map(lo, hi, ramp, m, ctx)
    option["grid"] = {"left": 8, "right": 16, "top": 10, "bottom": 44, "containLabel": True}
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m)}})
    ctx.decisions.append(f"columns are {x}, rows are {rows_col}; darker means bigger"
                         + ("; colours diverge from zero" if diverging else ""))  # fmt: skip
    if not show_labels:
        ctx.decisions.append(
            f"values are not written in the cells: {len(data):,} cells are too many to read"
        )
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(x_values), series=1, rows=len(data), x_time=ctx.prof[x].role == "time",
                     negative=lo < 0)  # fmt: skip
    return figure(
        ctx, ctx.title([m], [x, rows_col]), option, height or max(260, 28 * len(row_values) + 110)
    )


def calendar_heatmap(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    """One coloured square per day, laid out like a calendar (weeks across, weekdays down)."""
    dims = ctx.dims()
    if len(dims) != 1 or ctx.prof[dims[0]].role != "time":
        raise InvalidSpecError("a calendar heatmap needs x=<date column> and y=<measure>")
    x = dims[0]
    measures = ctx.measures()
    m = measures[0]
    result = aggregate(frame, x, [m], freq="day", prof=ctx.prof, missing="connect")
    vals = result.values.dropna(subset=[x])
    days = pd.to_datetime(vals[x])
    years = sorted(set(days.dt.year))
    if len(years) > MAX_YEARS:
        ctx.notes.append(f"showing the last {MAX_YEARS} of {len(years)} years")
        years = years[-MAX_YEARS:]
    keep = days.dt.year.isin(years)
    vals, days = vals[keep], days[keep]
    from tabsight.formats import format_date

    data: list[dict[str, Any]] = [{"name": format_date(d, "day", locale=ctx.locale), "value": [d.strftime("%Y-%m-%d"), num(v)]}
            for d, v in zip(days, vals[m.label], strict=True)]  # fmt: skip
    lo, hi, ramp, _ = scale((d["value"][1] for d in data), ctx)
    t = ctx.theme
    calendars, series = [], []
    for i, year in enumerate(years):
        calendars.append({
            "top": 30 + i * 150, "left": 50, "right": 20, "cellSize": ["auto", 15], "range": str(year),
            "itemStyle": {"color": t.tile, "borderColor": t.grid, "borderWidth": 1},
            "splitLine": {"lineStyle": {"color": t.border}},
            "yearLabel": {"color": t.text_secondary}, "monthLabel": {"color": t.text_secondary, "nameMap": "EN"},
            "dayLabel": {"color": t.text_secondary, "firstDay": 1, "nameMap": "EN"},
        })  # fmt: skip
        series.append({"type": "heatmap", "coordinateSystem": "calendar", "calendarIndex": i,
                       "name": ctx.measure_title(m), "data": [d for d in data if d["value"][0].startswith(str(year))]})  # fmt: skip
    option = _build._base(ctx)
    option["calendar"] = calendars
    option["series"] = series
    option["visualMap"] = visual_map(lo, hi, ramp, m, ctx, seriesIndex=list(range(len(series))))
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m)}})
    ctx.decisions.append(
        "one square per day: weeks run across, Monday to Sunday down; days with no data are blank"
    )
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(data), series=1, rows=len(data), x_time=True, negative=lo < 0)
    return figure(ctx, ctx.title([m], [x]), option, height or 70 + 150 * len(years))


def sankey(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    """Flows from a source column to a target column, widths by the measure."""
    spec = ctx.spec
    source, target = spec.source, spec.target
    if not source or not target:
        raise InvalidSpecError(
            "a Sankey diagram needs source=<column> and target=<column> (and y=<measure>)"
        )
    for col in (source, target):
        if col not in ctx.prof:
            from tabsight.charts import _missing

            raise _missing(col, ctx.prof)
    if source == target:
        raise InvalidSpecError("source and target must be different columns")
    measures = ctx.measures() if spec.y is not None else []
    from tabsight.aggregate import Measure

    m = measures[0] if measures else Measure(None, "count")
    if m.agg not in ("sum", "count"):
        raise InvalidSpecError(
            f"flow widths must add up, but {m.label} is {m.agg}; use a sum or a count"
        )
    result = aggregate(frame, [source, target], [m], prof=ctx.prof, missing="connect")
    vals = result.values
    links = []
    for _, r in vals.iterrows():
        v = num(r[m.label])
        if v is None or v <= 0:
            continue
        links.append((str(r[source]), str(r[target]), v))
    links.sort(key=lambda link: -link[2])
    dropped = len(links) - MAX_LINKS
    if dropped > 0:
        ctx.notes.append(f"showing the {MAX_LINKS} largest of {len(links)} flows")
        links = links[:MAX_LINKS]
    # A place on both sides (A -> B and B -> A) would be a cycle, which a Sankey can't draw:
    # the target side gets its own node, marked with an arrow.
    sources = {s for s, _, _ in links}
    renamed = False
    fixed = []
    for s, t_, v in links:
        if t_ in sources:
            t_ = f"→ {t_}"
            renamed = True
        fixed.append((s, t_, v))
    if renamed:
        ctx.decisions.append(
            "names that are both a source and a target appear twice; the target copy is marked →"
        )
    nodes = list(dict.fromkeys([s for s, _, _ in fixed] + [t_ for _, t_, _ in fixed]))
    option = _build._base(ctx)
    option["series"] = [{
        "type": "sankey", "name": ctx.measure_title(m), "left": 8, "right": 120, "top": 10, "bottom": 10,
        "nodeGap": 10, "nodeWidth": 14, "layoutIterations": 32, "emphasis": {"focus": "adjacency"},
        "data": [{"name": n, "itemStyle": {"color": ctx.colors.color(n.removeprefix("→ "))}} for n in nodes],
        "links": [{"source": s, "target": t_, "value": v} for s, t_, v in fixed],
        "lineStyle": {"color": "gradient", "opacity": 0.35, "curveness": 0.5},
        "label": {"color": ctx.theme.text, "fontSize": 11},
    }]  # fmt: skip
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m)}})
    ctx.decisions.append(f"flows from {source} (left) to {target} (right); band width is the value")
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(nodes), series=1, rows=len(fixed), x_time=False, negative=False)
    from tabsight.charts import _pretty

    title = (
        spec.title or f"{_pretty(ctx.measure_title(m))} from {_pretty(source)} to {_pretty(target)}"
    )
    return figure(ctx, title, option, height or max(320, 22 * len(nodes)))
