"""Comparison and single-value extras: lollipop, bullet, gauge, and combo (bars + line)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import Measure, aggregate
from tabsight.charts import _build
from tabsight.charts._common import figure, item_tooltip, mode, nice_ceiling, num
from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError, safe_repr

if TYPE_CHECKING:
    from tabsight.charts import _Context

__all__ = ["bullet", "combo", "gauge", "lollipop_from_bars"]


def lollipop_from_bars(option: dict[str, Any], horizontal: bool, ctx: _Context) -> dict[str, Any]:
    """Turn a single-series bar option into a lollipop: a thin stem and a dot at the value."""
    bar = option["series"][0]
    values = [d["value"] if isinstance(d, dict) else d for d in bar["data"]]
    color = ctx.colors.palette[0]
    bar.update({"barWidth": 2, "itemStyle": {"color": color, "borderRadius": 0}})
    bar.pop("barCategoryGap", None)
    label = bar.pop("label", None)
    dot: dict[str, Any] = {"type": "scatter", "name": bar["name"], "data": values, "symbolSize": 11,
                           "itemStyle": {"color": color}, "z": 3, "tooltip": {"show": False}}  # fmt: skip
    if label:
        label["position"] = "right" if horizontal else "top"
        dot["label"] = label
    option["series"] = [bar, dot]
    ctx.decisions.append(
        "a lollipop: a thin stem from zero and a dot at the value, lighter than bars"
    )
    return option


def _goal(frame: pd.DataFrame, ctx: _Context) -> tuple[Measure | None, float | None]:
    goal = ctx.spec.options.get("goal")
    if goal is None:
        return None, None
    if isinstance(goal, str):
        if goal not in ctx.prof:
            raise InvalidSpecError(f"goal column {safe_repr(goal)} not found")
        field = ctx.prof[goal]
        agg = field.agg if field.agg in ("sum", "mean", "median", "min", "max") else "sum"
        return Measure(goal, agg), None
    return None, float(goal)


# ---------------------------------------------------------------- bullet


def bullet(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    measures = ctx.measures()
    if len(measures) != 1:
        raise InvalidSpecError("a bullet chart shows one measure against a goal")
    m = measures[0]
    goal_m, goal_n = _goal(frame, ctx)
    if goal_m is None and goal_n is None:
        raise InvalidSpecError("a bullet chart needs goal=<number or column with the target>")
    dims = ctx.dims()
    if len(dims) > 1:
        raise InvalidSpecError("a bullet chart takes at most one x column")
    asked = [m] + ([goal_m] if goal_m else [])
    result = aggregate(frame, dims or None, asked, prof=ctx.prof, missing="connect")
    ctx.notes.extend(result.notes)
    vals = result.values
    from tabsight.charts import _labels

    labels = (
        _labels(vals[dims[0]], ctx.prof[dims[0]].grain, ctx, compact=False)
        if dims
        else [ctx.measure_title(m)]
    )
    actual = [num(v) for v in vals[m.label]]
    goals = [num(v) for v in vals[goal_m.label]] if goal_m else [goal_n] * len(actual)
    dark = mode(ctx)
    data = []
    for a, g in zip(actual, goals, strict=True):
        item: dict[str, Any] = {"value": a}
        if g is not None:
            share = f" ({a / g:.0%} of it)" if a is not None and g else ""
            item["note"] = f"goal {ctx.fmt(g, m, 'full')}{share}"
        data.append(item)
    option = _build._base(ctx)
    t = ctx.theme
    option["yAxis"] = _build._category_axis(labels, ctx, horizontal=True, gap=True)
    option["xAxis"] = _build._value_axis(ctx.js(m, "compact"), ctx)
    option["series"] = [
        {"type": "bar", "name": "Goal", "data": goals, "barWidth": 22, "barGap": "-100%",
         "itemStyle": {"color": t.grid}, "silent": True, "z": 1},
        {"type": "bar", "name": ctx.measure_title(m), "data": data, "barWidth": 9, "z": 2,
         "itemStyle": {"color": t.text if dark == "light" else "#d8dee6"}},
        {"type": "scatter", "name": "Goal marker", "data": goals, "symbol": "rect", "symbolSize": [3, 26],
         "itemStyle": {"color": "#c4572a" if dark == "light" else "#e07b4c"}, "z": 3, "silent": True},
    ]  # fmt: skip
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, m)}})
    option["grid"] = {"left": 8, "right": 24, "top": 16, "bottom": 8, "containLabel": True}
    ctx.decisions.append(
        "the dark bar is the actual value, the pale band and the orange mark the goal"
    )
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(labels), series=1, rows=len(labels), x_time=False,
                     negative=any((a or 0) < 0 for a in actual))  # fmt: skip
    return figure(
        ctx,
        ctx.title([m], dims) + " against goal",
        option,
        height or max(160, 46 * len(labels) + 40),
    )


# ---------------------------------------------------------------- gauge


def gauge(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    measures = ctx.measures()
    if len(measures) != 1 or ctx.spec.x is not None:
        raise InvalidSpecError("a gauge shows one number: pass y= and leave x= out")
    m = measures[0]
    goal_m, goal_n = _goal(frame, ctx)
    asked = [m] + ([goal_m] if goal_m else [])
    result = aggregate(frame, None, asked, prof=ctx.prof, missing="connect")
    value = num(result.values[m.label].iloc[0]) if len(result.values) else None
    goal = num(result.values[goal_m.label].iloc[0]) if goal_m else goal_n
    if value is not None and value < 0:
        raise InvalidSpecError(f"a gauge starts at zero, and {m.label} is negative; use a KPI card")
    top = goal if goal and goal > 0 else nice_ceiling((value or 0) * 1.1)
    if goal:
        ctx.decisions.append("the dial ends at the goal")
    else:
        ctx.decisions.append("no goal= given, so the dial ends at a round number above the value")
    over = value is not None and value > top
    if over:
        top = nice_ceiling(value * 1.05)  # type: ignore[operator]
        ctx.notes.append("the value is above the goal; the dial was extended to show it")
    t = ctx.theme
    accent = ctx.colors.palette[0]
    option = _build._base(ctx)
    option["series"] = [{
        "type": "gauge", "name": ctx.measure_title(m), "min": 0, "max": top, "startAngle": 210, "endAngle": -30,
        "progress": {"show": True, "width": 16, "itemStyle": {"color": accent}},
        "axisLine": {"lineStyle": {"width": 16, "color": [[1, t.grid]]}},
        "pointer": {"show": False}, "splitLine": {"show": False}, "axisTick": {"show": False},
        "axisLabel": {"distance": 22, "color": t.text_secondary, "fontSize": 11,
                      "formatter": {"$fmt": ctx.js(m, "compact")}},
        "splitNumber": 4,
        "detail": {"valueAnimation": False, "offsetCenter": [0, "10%"], "fontSize": 30, "fontWeight": 650,
                   "color": t.text, "formatter": {"$fmt": ctx.js(m, "compact")}},
        "title": {"offsetCenter": [0, "42%"], "color": t.text_secondary, "fontSize": 13},
        "data": [{"value": value, "name": f"{value / goal:.0%} of goal" if goal and value is not None else ""}],
    }]  # fmt: skip
    if goal:
        option["series"][0]["markLine"] = None
    ctx.describe_format([m], "")
    ctx.facts.update(categories=1, series=1, rows=1, x_time=False, negative=False)
    title = ctx.spec.title or _pretty_measure(ctx, m)
    return figure(ctx, title, option, height or 300)


def _pretty_measure(ctx: _Context, m: Measure) -> str:
    from tabsight.charts import _pretty

    return _pretty(ctx.measure_title(m))


# ---------------------------------------------------------------- combo


def combo(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    measures = ctx.measures()
    if len(measures) < 2:
        raise InvalidSpecError(
            "a combo chart needs y= with two or more measures (bars, then lines)"
        )
    dims = ctx.dims()
    if len(dims) != 1:
        raise InvalidSpecError("a combo chart takes one x column")
    x = dims[0]
    time = ctx.prof[x].role == "time"
    result = aggregate(frame, x, measures, freq=ctx.spec.options.get("freq"), sort=ctx.spec.sort, prof=ctx.prof,
                       missing="zero" if not time else None)  # fmt: skip
    ctx.notes.extend(result.notes)
    vals = result.values
    from tabsight.charts import _labels

    grain = ctx.spec.options.get("freq") or ctx.prof[x].grain
    labels = _labels(vals[x], grain, ctx, compact=len(vals) > 8)
    bar_m, line_ms = measures[0], measures[1:]
    units = {ctx.number_kwargs(mm)["unit"] for mm in measures}
    two_axes = (
        len({ctx.number_kwargs(bar_m)["unit"]} | {ctx.number_kwargs(mm)["unit"] for mm in line_ms})
        > 1
    )
    option = _build._base(ctx)
    left = _build._value_axis(ctx.js(bar_m, "compact"), ctx)
    left.update(
        {"name": bar_m.label, "nameTextStyle": {"color": ctx.theme.text_secondary, "align": "left"}}
    )
    axes = [left]
    if two_axes:
        right = _build._value_axis(ctx.js(line_ms[0], "compact"), ctx, scale=True)
        right.update({"splitLine": {"show": False}, "name": line_ms[0].label,
                      "nameTextStyle": {"color": ctx.theme.text_secondary, "align": "right"}})  # fmt: skip
        axes.append(right)
    option["xAxis"] = _build._category_axis(labels, ctx, horizontal=False, gap=True)
    option["yAxis"] = axes
    series: list[dict[str, Any]] = [{"type": "bar", "name": bar_m.label, "data": [num(v) for v in vals[bar_m.label]],
                                     "barCategoryGap": "35%", "itemStyle": {"color": ctx.colors.color(bar_m.label),
                                                                            "borderRadius": [3, 3, 0, 0]}}]  # fmt: skip
    for mm in line_ms:
        color = ctx.colors.color(mm.label)
        series.append({"type": "line", "name": mm.label, "yAxisIndex": 1 if two_axes else 0, "smooth": False,
                       "data": [num(v) for v in vals[mm.label]], "symbolSize": 6,
                       "lineStyle": {"width": 2, "color": color}, "itemStyle": {"color": color}})  # fmt: skip
    option["series"] = series
    option["legend"] = _build._legend(ctx)
    option["grid"] = {"left": 8, "right": 8, "top": 48, "bottom": 8, "containLabel": True}
    option["tooltip"].update({"trigger": "axis", "axisPointer": {"type": "shadow"}, "formatter": {"$tooltip": {
        "trigger": "axis", "fmt": ctx.js(bar_m, "full"),
        "series_fmt": {mm.label: ctx.js(mm, "full") for mm in measures}}}})  # fmt: skip
    ctx.decisions.append(
        f"{bar_m.label} as bars, {', '.join(mm.label for mm in line_ms)} as line(s)"
    )
    if two_axes:
        ctx.decisions.append(
            f"two axes because the units differ ({', '.join(sorted(units))}): bars on the left, lines on the right"
        )
    ctx.describe_format(measures, "")
    ctx.facts.update(categories=len(labels), series=len(series), rows=len(labels), x_time=time, x_ordered=time,
                     negative=False, two_axes=two_axes)  # fmt: skip
    return figure(ctx, ctx.title(measures, [x]), option, height or 420)
