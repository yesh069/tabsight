"""Part-to-whole and ranking charts: treemap, sunburst, waterfall, funnel and Pareto."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import aggregate
from tabsight.charts import _build
from tabsight.charts._common import (
    NEGATIVE,
    POSITIVE,
    fields_tooltip,
    figure,
    item_tooltip,
    mode,
    num,
)
from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError

if TYPE_CHECKING:
    from tabsight.aggregate import Measure
    from tabsight.charts import _Context

__all__ = ["funnel", "pareto", "tree", "waterfall"]

MAX_LEAVES = 500
MAX_PARETO = 30
_ADDITIVE = ("sum", "count")


def _one_measure(ctx: _Context, *, additive: bool) -> Measure:
    measures = ctx.measures()
    if len(measures) != 1:
        raise InvalidSpecError(f"a {ctx.spec.kind} shows one measure; pass a single y= column")
    m = measures[0]
    if additive and m.agg not in _ADDITIVE:
        raise InvalidSpecError(
            f"a {ctx.spec.kind} shows parts of a whole, but {m.label} is "
            f"{'averaged' if m.agg == 'mean' else m.agg}, which doesn't add up; use bars"
        )
    return m


def _dims(ctx: _Context, *, at_least: int = 1) -> list[str]:
    dims = ctx.dims() + ([ctx.spec.color] if ctx.spec.color else [])
    if len(dims) < at_least:
        raise InvalidSpecError(f"a {ctx.spec.kind} needs x=<column to group by>")
    return dims


def _pretty_title(ctx: _Context, m: Measure, dims: list[str]) -> str:
    return ctx.title([m], dims)


# ---------------------------------------------------------------- treemap and sunburst


def tree(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    kind = ctx.spec.kind
    dims = _dims(ctx)
    m = _one_measure(ctx, additive=True)
    result = aggregate(frame, dims, [m], prof=ctx.prof, missing="connect")
    ctx.notes.extend(result.notes)
    vals = result.values
    values = pd.to_numeric(vals[m.label], errors="coerce")
    negative = vals[values < 0]
    if len(negative):
        ctx.notes.append(
            f"{len(negative):,} group(s) with a negative total can't be drawn as areas and are left out"
        )
    vals = vals[values > 0]
    if len(vals) > MAX_LEAVES:
        vals = vals.sort_values(m.label, ascending=False).head(MAX_LEAVES)
        ctx.notes.append(f"showing the {MAX_LEAVES:,} largest of {len(result.values):,} groups")
    total = float(pd.to_numeric(vals[m.label]).sum()) or 1.0
    root: dict[str, Any] = {"children": {}}
    for _, row in vals.iterrows():
        node = root
        for d in dims:
            label = "Unknown" if pd.isna(row[d]) else str(row[d])
            node = node["children"].setdefault(label, {"name": label, "value": 0.0, "children": {}})
            node["value"] += float(row[m.label])

    def emit(node: dict[str, Any], depth: int, color: str | None) -> dict[str, Any]:
        item: dict[str, Any] = {"name": node["name"], "value": round(node["value"], 10),
                                "note": f"{node['value'] / total:.1%} of the total"}  # fmt: skip
        if depth == 0:
            color = ctx.colors.color(node["name"])
        if color:
            item["itemStyle"] = {"color": color}
        kids = sorted(node["children"].values(), key=lambda n: -n["value"])
        if kids:
            item["children"] = [emit(k, depth + 1, color) for k in kids]
        return item

    data = [emit(n, 0, None) for n in sorted(root["children"].values(), key=lambda n: -n["value"])]
    option = _build._base(ctx)
    option["tooltip"].update(
        {"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m, path=True)}}
    )
    t = ctx.theme
    if kind == "treemap":
        option["series"] = [{
            "type": "treemap", "name": ctx.measure_title(m), "data": data, "roam": False, "nodeClick": "zoomToNode",
            "top": 8, "left": 4, "right": 4, "bottom": 30, "leafDepth": len(dims) if len(dims) > 1 else None,
            "breadcrumb": {"show": len(dims) > 1, "bottom": 4, "itemStyle": {"color": t.header, "textStyle": {"color": t.text}}},
            "label": {"show": True, "formatter": "{b}", "fontSize": 11},
            "upperLabel": {"show": len(dims) > 1, "height": 20, "color": "#ffffff", "fontWeight": 600},
            "itemStyle": {"borderColor": t.tile, "borderWidth": 1, "gapWidth": 1},
            "levels": [{"itemStyle": {"borderWidth": 2, "gapWidth": 2, "borderColor": t.tile}},
                       {"colorSaturation": [0.35, 0.6], "itemStyle": {"gapWidth": 1, "borderColorSaturation": 0.6}}],
        }]  # fmt: skip
        ctx.decisions.append("area is proportional to the value; click a box to zoom into it")
    else:
        option["series"] = [{
            "type": "sunburst", "name": ctx.measure_title(m), "data": data, "radius": ["12%", "92%"], "sort": None,
            "label": {"rotate": "radial", "fontSize": 10, "minAngle": 6},
            "itemStyle": {"borderColor": t.tile, "borderWidth": 1},
            "levels": [{}, {"label": {"rotate": "tangential"}}, {"itemStyle": {"opacity": 0.85}}, {"itemStyle": {"opacity": 0.7}}],
        }]  # fmt: skip
        ctx.decisions.append(
            "the inner ring is the first level; each ring outward splits it further"
        )
    if len(dims) > 1:
        ctx.decisions.append(f"levels: {' > '.join(dims)}")
    ctx.describe_format([m], "")
    ctx.facts.update(
        categories=len(vals), series=1, rows=len(vals), x_time=False, negative=bool(len(negative))
    )
    return figure(ctx, _pretty_title(ctx, m, dims), option, height or 480)


# ---------------------------------------------------------------- waterfall


def waterfall(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    dims = _dims(ctx)
    if len(dims) != 1:
        raise InvalidSpecError("a waterfall takes one x column of steps")
    x = dims[0]
    m = _one_measure(ctx, additive=True)
    time = ctx.prof[x].role == "time"
    if ctx.spec.sort is None and not time and not ctx.prof[x].ordered:
        order = tuple(
            dict.fromkeys(frame[x].dropna().astype(str))
        )  # the steps in the order they appear
        result = aggregate(frame, x, [m], sort=order, prof=ctx.prof, missing="connect")
        ctx.decisions.append("steps keep the order they appear in the data; sort= changes it")
    else:
        result = aggregate(frame, x, [m], freq=ctx.spec.options.get("freq"), sort=ctx.spec.sort, prof=ctx.prof,
                           missing="connect")  # fmt: skip
        ctx.decisions.append("steps in time order" if time else "steps in the order asked")
    ctx.notes.extend(result.notes)
    vals = result.values
    from tabsight.charts import _labels

    grain = ctx.spec.options.get("freq") or ctx.prof[x].grain
    labels = _labels(vals[x], grain, ctx, compact=len(vals) > 8)
    dark = mode(ctx)
    data = []
    running = 0.0
    for i, (label, v) in enumerate(zip(labels, vals[m.label], strict=True)):
        change = num(v) or 0.0
        lo, hi = running, running + change
        running = hi
        data.append({"name": label, "value": [i, lo, hi, change, running],
                     "itemStyle": {"color": POSITIVE[dark] if change >= 0 else NEGATIVE[dark]}})  # fmt: skip
    if ctx.spec.options.get("total", True):
        labels = [*labels, "Total"]
        data.append({"name": "Total", "value": [len(data), 0.0, running, running, running],
                     "itemStyle": {"color": ctx.theme.text_secondary}})  # fmt: skip
        ctx.decisions.append("the last bar is the total, from zero")
    option = _build._base(ctx)
    option["xAxis"] = _build._category_axis(labels, ctx, horizontal=False, gap=True)
    option["yAxis"] = _build._value_axis(ctx.js(m, "compact"), ctx)
    option["series"] = [{"type": "custom", "name": ctx.measure_title(m), "renderItem": {"$render": "range"},
                         "encode": {"x": 0, "y": [1, 2]}, "data": data}]  # fmt: skip
    fmt = ctx.js(m, "full")
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": fields_tooltip(
        [("Change", 3, fmt), ("Running total", 4, fmt)])}})  # fmt: skip
    option["grid"] = {"left": 8, "right": 24, "top": 20, "bottom": 8, "containLabel": True}
    ctx.decisions.append(
        "each bar starts where the previous one ended: blue adds, orange takes away"
    )
    ctx.describe_format([m], "")
    ctx.facts.update(
        categories=len(vals), series=1, rows=len(vals), x_time=time, x_ordered=True, negative=False
    )
    return figure(ctx, _pretty_title(ctx, m, [x]), option, height or 420)


# ---------------------------------------------------------------- funnel


def funnel(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    dims = _dims(ctx)
    if len(dims) != 1:
        raise InvalidSpecError("a funnel takes one x column of stages")
    x = dims[0]
    m = _one_measure(ctx, additive=True)
    keep_order = ctx.spec.sort is not None or bool(ctx.prof[x].ordered)
    result = aggregate(frame, x, [m], sort=ctx.spec.sort, prof=ctx.prof, missing="connect")
    ctx.notes.extend(result.notes)
    vals = result.values
    rows = [(_name(k), num(v) or 0.0) for k, v in zip(vals[x], vals[m.label], strict=True)]
    if not keep_order:
        rows.sort(key=lambda r: -r[1])
        ctx.decisions.append(
            "stages sorted largest first; pass sort=[...] or an ordered column for your own order"
        )
    else:
        ctx.decisions.append("stages in the order given")
    if any(b > a for (_, a), (_, b) in itertools.pairwise(rows)):
        ctx.notes.append(
            "some stages are bigger than the one before, so a funnel shape misleads; bars may be clearer"
        )
    first = rows[0][1] if rows else 0.0
    data = []
    for i, (name, v) in enumerate(rows):
        note = (
            ""
            if i == 0
            else f"{v / rows[i - 1][1]:.0%} of the previous stage"
            if rows[i - 1][1]
            else ""
        )
        if i and first:
            note += f"{'; ' if note else ''}{v / first:.0%} of the first"
        item: dict[str, Any] = {
            "name": name,
            "value": v,
            "itemStyle": {"color": ctx.colors.palette[i % len(ctx.colors.palette)]},
        }
        if note:
            item["note"] = note
        data.append(item)
    option = _build._base(ctx)
    option["series"] = [{"type": "funnel", "name": ctx.measure_title(m), "data": data, "sort": "none",
                         "left": "10%", "width": "80%", "top": 10, "bottom": 10, "gap": 2, "minSize": "8%",
                         "label": {"show": True, "position": "inside", "formatter": "{b}", "color": "#ffffff"},
                         "itemStyle": {"borderColor": ctx.theme.tile, "borderWidth": 1}}]  # fmt: skip
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m)}})
    ctx.decisions.append(
        "hover a stage to see what share of the previous and first stages it keeps"
    )
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(rows), series=1, rows=len(rows), x_time=False, negative=False)
    return figure(ctx, _pretty_title(ctx, m, [x]), option, height or 420)


# ---------------------------------------------------------------- Pareto


def pareto(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    dims = _dims(ctx)
    if len(dims) != 1:
        raise InvalidSpecError("a Pareto chart takes one x column")
    x = dims[0]
    m = _one_measure(ctx, additive=True)
    top = ctx.spec.top or MAX_PARETO
    result = aggregate(frame, x, [m], top=top, prof=ctx.prof, missing="connect")
    ctx.notes.extend(result.notes)
    vals = result.values
    rows = [(_name(k), num(v) or 0.0) for k, v in zip(vals[x], vals[m.label], strict=True)]
    if any(v < 0 for _, v in rows):
        raise InvalidSpecError(
            f"a Pareto chart needs totals of zero or more; {m.label} has negative ones"
        )
    if result.other:
        ctx.notes.append(
            f"showing the top {top} of {result.categories.get(x, len(rows))}; the rest are in Other"
        )
    total = sum(v for _, v in rows) or 1.0
    running, cumulative = 0.0, []
    for _, v in rows:
        running += v
        cumulative.append(round(running / total, 6))
    reach = next((i + 1 for i, c in enumerate(cumulative) if c >= 0.8), len(rows))
    ctx.decisions.append(
        f"bars largest first; the line adds them up: {reach} of {len(rows)} make 80% of the total"
    )
    labels = [r[0] for r in rows]
    from tabsight.formats import js_spec

    pct = js_spec("percent", "full", locale=ctx.locale, decimals=0, percent_scale="fraction")
    option = _build._base(ctx)
    option["xAxis"] = _build._category_axis(labels, ctx, horizontal=False, gap=True)
    share_axis = _build._value_axis(pct, ctx)
    share_axis.update({"max": 1, "min": 0, "splitLine": {"show": False}})
    option["yAxis"] = [_build._value_axis(ctx.js(m, "compact"), ctx), share_axis]
    option["series"] = [
        {"type": "bar", "name": ctx.measure_title(m), "data": [r[1] for r in rows], "barCategoryGap": "25%",
         "itemStyle": {"color": ctx.colors.palette[0], "borderRadius": [3, 3, 0, 0]}},
        {"type": "line", "name": "Running share", "yAxisIndex": 1, "data": cumulative, "smooth": False,
         "symbolSize": 5, "itemStyle": {"color": NEGATIVE[mode(ctx)]}, "lineStyle": {"width": 2},
         "markLine": {"silent": True, "symbol": "none", "data": [{"yAxis": 0.8}],
                      "lineStyle": {"type": "dashed", "color": ctx.theme.text_secondary}, "label": {"show": False}}},
    ]  # fmt: skip
    option["legend"] = _build._legend(ctx)
    option["grid"] = {"left": 8, "right": 8, "top": 40, "bottom": 8, "containLabel": True}
    option["tooltip"].update({"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": {"$tooltip": {
        "trigger": "axis", "fmt": ctx.js(m, "full"),
        "series_fmt": {ctx.measure_title(m): ctx.js(m, "full"), "Running share": pct}}}})  # fmt: skip
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(rows), series=2, rows=len(rows), x_time=False, negative=False)
    return figure(ctx, _pretty_title(ctx, m, [x]), option, height or 420)


def _name(value: object) -> str:
    """A stage or bar name; a missing value is "Unknown", never "nan"."""
    if value is None or (isinstance(value, float) and value != value):
        from tabsight.i18n import text

        return text("unknown")
    return str(value)
