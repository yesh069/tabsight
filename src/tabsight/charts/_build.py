"""ECharts option builders. Everything returned is plain JSON (formats as ``$fmt`` objects)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import Measure
from tabsight.colors import natural_key

if TYPE_CHECKING:
    from tabsight.charts import _Context

OTHER_COLOR = "#bab0ac"
ZOOM_AFTER = 15
MARKERS_BELOW = 30
LABELS_UP_TO = 8


def default_height(kind: str, n: int) -> int:
    if kind == "hbar":
        return max(260, min(1400, 30 * n + 90))
    if kind == "sparkline":
        return 90
    if kind == "donut":
        return 380
    return 420


def _base(ctx: _Context) -> dict[str, Any]:
    t = ctx.theme
    return {
        "backgroundColor": "transparent",
        "animationDuration": 400,
        "textStyle": {"fontFamily": t.font, "color": t.text},
        "aria": {"enabled": True},
        "tooltip": {
            "backgroundColor": t.tile,
            "borderColor": t.border,
            "borderWidth": 1,
            "padding": [8, 10],
            "textStyle": {"color": t.text, "fontSize": 12, "fontFamily": t.font},
            "extraCssText": "border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.12);",
        },
    }


def _category_axis(
    labels: list[str], ctx: _Context, *, horizontal: bool, gap: bool
) -> dict[str, Any]:
    t = ctx.theme
    longest = max((len(lb) for lb in labels), default=0)
    label: dict[str, Any] = {"color": t.text_secondary, "interval": 0, "hideOverlap": False}
    if horizontal:
        label.update({"width": 180, "overflow": "truncate"})
    elif longest > 10 or len(labels) > 8:
        label["rotate"] = 30
    return {
        "type": "category",
        "data": labels,
        "boundaryGap": gap,
        "inverse": horizontal,  # largest bar at the top
        "axisLine": {"lineStyle": {"color": t.axis}},
        "axisTick": {"show": False},
        "axisLabel": label,
    }


def _dates_may_skip(axis: dict[str, Any], x: str, labels: list[str], ctx: _Context) -> None:
    """Dates are in order, so a skipped label can't be misread: let ECharts drop the ones
    that would overlap. Category labels are never skipped (a bar must be named)."""
    if ctx.prof[x].role != "time" or len(labels) <= 12:
        return
    axis["axisLabel"] = {**axis["axisLabel"], "interval": "auto", "hideOverlap": True}
    ctx.facts["date_labels_thinned"] = True
    ctx.decisions.append("dates are in order, so date labels that would overlap are left out")


def _value_axis(fmt: dict[str, Any], ctx: _Context, *, scale: bool = False) -> dict[str, Any]:
    t = ctx.theme
    return {
        "type": "value",
        "scale": scale,
        "axisLine": {"show": False},
        "axisTick": {"show": False},
        "splitLine": {"lineStyle": {"color": t.grid}},
        "axisLabel": {"color": t.text_secondary, "formatter": {"$fmt": fmt}},
    }


def _legend(ctx: _Context) -> dict[str, Any]:
    return {
        "top": 0,
        "left": 0,
        "type": "scroll",
        "icon": "roundRect",
        "itemWidth": 10,
        "itemHeight": 10,
        "textStyle": {"color": ctx.theme.text_secondary},
    }


def _series_values(
    values: pd.DataFrame, x: str, x_values: list[Any], color: str | None, label: str
) -> dict[str, list[Any]]:
    """{series name: values in x order}. Without colour, one series named after the measure."""
    if color is None:
        lookup = dict(zip(values[x], values[label], strict=False))
        return {label: [_num(lookup.get(v)) for v in x_values]}
    out: dict[str, list[Any]] = {}
    names = sorted({str(c) for c in values[color].dropna()}, key=_series_order)
    if values[color].isna().any():
        names.append(_unknown())
    for name in names:
        sub = values[
            values[color].astype("object").where(values[color].notna(), _unknown()).astype(str)
            == name
        ]
        lookup = dict(zip(sub[x], sub[label], strict=False))
        out[name] = [_num(lookup.get(v)) for v in x_values]
    return out


def _series_order(name: str) -> tuple[Any, ...]:
    return (name.startswith("Other ("), natural_key(name))


def _unknown() -> str:
    from tabsight.i18n import text

    return text("unknown")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _color_for(name: str, ctx: _Context) -> str:
    return OTHER_COLOR if name.startswith("Other (") else ctx.colors.color(name)


def bars(
    values: pd.DataFrame,
    x: str,
    x_values: list[Any],
    labels: list[str],
    measures: list[Measure],
    color: str | None,
    kind: str,
    other_x: set[Any],
    ctx: _Context,
) -> dict[str, Any]:
    horizontal = kind == "hbar"
    option = _base(ctx)
    series: list[dict[str, Any]] = []
    series_fmt: dict[str, dict[str, Any]] = {}
    m0 = measures[0]
    if kind == "stacked100_bar":
        tooltip_fmt = {**ctx.js(m0, "full"), "unit": "percent", "percent_scale": "fraction", "decimals": None,
                       "pattern": None}  # fmt: skip
        axis_fmt = {**tooltip_fmt, "style": "compact"}
    else:
        tooltip_fmt, axis_fmt = ctx.js(m0, "full"), ctx.js(m0, "compact")

    if color is None:
        for m in measures:
            data = _series_values(values, x, x_values, None, m.label)[m.label]
            single = len(measures) == 1
            items: list[Any] = []
            for v, xv in zip(data, x_values, strict=True):
                if single and xv in other_x:
                    items.append({"value": v, "itemStyle": {"color": OTHER_COLOR}})
                else:
                    items.append(v)
            s: dict[str, Any] = {
                "type": "bar",
                "name": m.label,
                "data": items,
                "barCategoryGap": "35%",
                "itemStyle": {
                    "color": ctx.colors.palette[0] if single else ctx.colors.color(m.label),
                    "borderRadius": [0, 3, 3, 0] if horizontal else [3, 3, 0, 0],
                },
            }
            if single and len(x_values) <= LABELS_UP_TO:
                s["label"] = {"show": True, "position": "right" if horizontal else "top",
                              "color": ctx.theme.text_secondary, "fontSize": 11,
                              "formatter": {"$label": ctx.js(m, "compact")}}  # fmt: skip
            series.append(s)
            series_fmt[m.label] = ctx.js(m, "full")
    else:
        raw = _series_values(values, x, x_values, color, m0.label)
        if kind == "stacked100_bar":
            totals = [
                sum(abs(v) for v in col if v is not None) for col in zip(*raw.values(), strict=True)
            ]
            raw = {k: [(v / t if v is not None and t else None) for v, t in zip(vs, totals, strict=True)]
                   for k, vs in raw.items()}  # fmt: skip
        stack = "total" if kind in ("stacked_bar", "stacked100_bar") else None
        for name, data in raw.items():
            s = {"type": "bar", "name": name, "data": data, "barCategoryGap": "30%",
                 "itemStyle": {"color": _color_for(name, ctx)}}  # fmt: skip
            if stack:
                s["stack"] = stack
            series.append(s)
            series_fmt[name] = tooltip_fmt

    cat = _category_axis(labels, ctx, horizontal=horizontal, gap=True)
    _dates_may_skip(cat, x, labels, ctx)
    val = _value_axis(axis_fmt, ctx)
    if kind == "stacked100_bar":
        val["max"] = 1
    option["xAxis"], option["yAxis"] = (val, cat) if horizontal else (cat, val)
    option["series"] = series
    option["tooltip"].update({"trigger": "axis", "axisPointer": {"type": "shadow"},
                              "formatter": {"$tooltip": {"trigger": "axis", "fmt": tooltip_fmt,
                                                         "series_fmt": series_fmt}}})  # fmt: skip
    multi = len(series) > 1
    if multi:
        option["legend"] = _legend(ctx)
    option["grid"] = {
        "left": 8,
        "right": 24,
        "top": 40 if multi else 20,
        "bottom": 8,
        "containLabel": True,
    }
    if not horizontal and len(labels) > ZOOM_AFTER:
        option["dataZoom"] = [{"type": "slider", "height": 18, "bottom": 4}, {"type": "inside"}]
        option["grid"]["bottom"] = 36
    return option


def lines(
    values: pd.DataFrame,
    x: str,
    x_values: list[Any],
    labels: list[str],
    measures: list[Measure],
    color: str | None,
    kind: str,
    ctx: _Context,
) -> dict[str, Any]:
    option = _base(ctx)
    m0 = measures[0]
    area = kind in ("area", "stacked_area", "sparkline")
    stacked = kind == "stacked_area"
    series: list[dict[str, Any]] = []
    series_fmt: dict[str, dict[str, Any]] = {}
    if color is None:
        raw = {
            m.label: _series_values(values, x, x_values, None, m.label)[m.label] for m in measures
        }
        fmts = {m.label: ctx.js(m, "full") for m in measures}
    else:
        raw = _series_values(values, x, x_values, color, m0.label)
        fmts = dict.fromkeys(raw, ctx.js(m0, "full"))
    single = len(raw) == 1
    for name, data in raw.items():
        line_color = ctx.colors.palette[0] if single else _color_for(name, ctx)
        s: dict[str, Any] = {
            "type": "line",
            "name": name,
            "data": data,
            "smooth": False,
            "connectNulls": False,
            "showSymbol": len(x_values) < MARKERS_BELOW and kind != "sparkline",
            "symbolSize": 6,
            "lineStyle": {"width": 2 if kind != "sparkline" else 1.5, "color": line_color},
            "itemStyle": {"color": line_color},
        }
        if area:
            s["areaStyle"] = {"opacity": 0.55 if stacked else 0.16, "color": line_color}
        if stacked:
            s["stack"] = "total"
        series.append(s)
        series_fmt[name] = fmts[name]
    option["series"] = series
    option["tooltip"].update({"trigger": "axis", "axisPointer": {"type": "line"},
                              "formatter": {"$tooltip": {"trigger": "axis", "fmt": ctx.js(m0, "full"),
                                                         "series_fmt": series_fmt}}})  # fmt: skip
    if kind == "sparkline":
        option["xAxis"] = {"type": "category", "data": labels, "show": False, "boundaryGap": False}
        option["yAxis"] = {"type": "value", "show": False, "scale": True}
        option["grid"] = {"left": 2, "right": 2, "top": 6, "bottom": 2}
        return option
    option["xAxis"] = _category_axis(labels, ctx, horizontal=False, gap=False)
    _dates_may_skip(option["xAxis"], x, labels, ctx)
    option["yAxis"] = _value_axis(ctx.js(m0, "compact"), ctx, scale=not area)
    multi = len(series) > 1
    if multi:
        option["legend"] = _legend(ctx)
        others = [s["name"] for s in series if str(s["name"]).startswith("Other (") and not stacked]
        if others:
            # An "Other" line is the total of several values, so it would tower over the
            # rest and flatten them. It starts hidden; one click on the legend shows it.
            option["legend"]["selected"] = {name: False for name in others}
            ctx.decisions.append(
                "the Other line starts hidden (click it in the legend): as a total of several "
                "values it would dwarf the others"
            )
    option["grid"] = {
        "left": 8,
        "right": 24,
        "top": 40 if multi else 20,
        "bottom": 8,
        "containLabel": True,
    }
    if len(labels) > 60:
        option["dataZoom"] = [{"type": "slider", "height": 18, "bottom": 4}, {"type": "inside"}]
        option["grid"]["bottom"] = 36
    return option


def donut(
    values: pd.DataFrame, x: str, labels: list[str], m: Measure, other_x: set[Any], ctx: _Context
) -> tuple[dict[str, Any], str]:
    nums = [_num(v) for v in values[m.label]]
    if any(v is not None and v < 0 for v in nums):
        x_values = list(values[x])
        return bars(values, x, x_values, labels, [m], None, "hbar", other_x, ctx), "hbar"
    option = _base(ctx)
    data = []
    for xv, label, v in zip(values[x], labels, nums, strict=True):
        item: dict[str, Any] = {"name": label, "value": v}
        item["itemStyle"] = {"color": OTHER_COLOR if xv in other_x else ctx.colors.color(label)}
        data.append(item)
    percent_fmt = {
        **ctx.js(m, "full"),
        "unit": "percent",
        "percent_scale": "whole",
        "decimals": None,
        "pattern": None,
    }
    option["series"] = [
        {
            "type": "pie",
            "radius": ["46%", "72%"],
            "center": ["50%", "54%"],
            "startAngle": 90,
            "percentPrecision": 1,
            "clockwise": True,
            "avoidLabelOverlap": True,
            "data": data,
            "itemStyle": {"borderColor": ctx.theme.tile, "borderWidth": 2},
            "label": {"color": ctx.theme.text_secondary, "formatter": "{b}  {d}%"},
            "labelLine": {"lineStyle": {"color": ctx.theme.axis}},
        }
    ]
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": {
        "trigger": "item", "fmt": ctx.js(m, "full"), "percent": True, "percent_fmt": percent_fmt}}})  # fmt: skip
    return option, "donut"
