"""Relationship and distribution charts: scatter, bubble, histogram, box plot, and lines over
a number (a real value axis instead of category labels)."""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from tabsight.aggregate import Measure, aggregate
from tabsight.charts import _build
from tabsight.charts._common import fields_tooltip, figure, item_tooltip, num
from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError, safe_repr

if TYPE_CHECKING:
    from tabsight.charts import _Context

__all__ = ["boxplot", "histogram", "numeric_lines", "scatter"]

MAX_POINTS = 5000  # scatter points drawn; more are sampled evenly (and the chart says so)
LARGE_MODE = 2000  # ECharts' fast drawing for many points
MAX_LINE_POINTS = 2000  # per line; more are thinned with LTTB, which keeps the shape
MAX_BOXES = 30
MAX_BINS = 30  # more bars than this read as noise; bins= can ask for more


def is_numeric(ctx: _Context, frame: pd.DataFrame, column: str) -> bool:
    """A column of numbers that is a quantity (not a date, ID or category)."""
    field = ctx.prof[column]
    col = frame[column]
    numbers = pd.api.types.is_numeric_dtype(col) and not pd.api.types.is_bool_dtype(col)
    # a run of unique numbers (a step, a row number) profiles as an ID but is a fine axis
    return field.role in ("measure", "coord") or (
        numbers and (field.role == "id" or (field.role == "dimension" and field.distinct > 20))
    )


def _measure_for(ctx: _Context, column: str) -> Measure:
    if column not in ctx.prof:
        from tabsight.charts import _missing

        raise _missing(column, ctx.prof)
    return Measure(column, "sum")  # formats by the column's unit; never aggregated here


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    from tabsight.read import read_numbers

    col = frame[column]
    if pd.api.types.is_numeric_dtype(col) and not pd.api.types.is_bool_dtype(col):
        return pd.to_numeric(col, errors="coerce").astype("float64")
    reading = read_numbers(col)
    values = reading.values if reading is not None else pd.to_numeric(col, errors="coerce")
    return pd.to_numeric(values, errors="coerce").astype("float64")


# ---------------------------------------------------------------- scatter and bubble


def scatter(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    """Two forms: x and y are number columns (one dot per row), or x is a category and y
    lists two or three measures (one dot per category, aggregated exactly)."""
    spec = ctx.spec
    if spec.x is None or spec.y is None:
        raise InvalidSpecError(f"a {spec.kind} needs x= and y=")
    x = spec.x if isinstance(spec.x, str) else None
    if x is None:
        raise InvalidSpecError(f"a {spec.kind} takes one x column")
    if x not in ctx.prof:
        from tabsight.charts import _missing

        raise _missing(x, ctx.prof)
    if is_numeric(ctx, frame, x):
        return _row_scatter(frame, ctx, height, x)
    return _grouped_scatter(frame, ctx, height, x)


def _row_scatter(frame: pd.DataFrame, ctx: _Context, height: int | None, x: str) -> Figure:
    spec = ctx.spec
    ys = [spec.y] if isinstance(spec.y, str) else list(spec.y or ())
    if len(ys) != 1:
        raise InvalidSpecError("with a number on x, pass one y= column (and size= for bubbles)")
    y = ys[0]
    size = spec.size
    if spec.kind == "bubble" and size is None:
        raise InvalidSpecError("a bubble chart needs size=<measure column>")
    mx, my = _measure_for(ctx, x), _measure_for(ctx, y)
    ms = _measure_for(ctx, size) if size else None
    cols = {"x": _numbers(frame, x), "y": _numbers(frame, y)}
    if size:
        cols["s"] = _numbers(frame, size)
    work = pd.DataFrame(cols)
    if spec.color:
        work["c"] = (
            frame[spec.color]
            .astype("object")
            .where(frame[spec.color].notna(), "Unknown")
            .astype(str)
        )
    complete = work.dropna(subset=list(cols))
    dropped = len(work) - len(complete)
    if dropped:
        ctx.notes.append(f"{dropped:,} row(s) without numbers in {x} and {y} are left out")
    if len(complete) > MAX_POINTS:
        step = len(complete) / MAX_POINTS
        complete = complete.iloc[[int(i * step) for i in range(MAX_POINTS)]]
        ctx.notes.append(
            f"showing an even sample of {MAX_POINTS:,} of {len(work) - dropped:,} points"
        )
    ctx.decisions.append(
        f"one dot per row: {x} across, {y} up; axes fit the data rather than start at zero"
    )
    biggest = float(complete["s"].abs().max()) if size and len(complete) else 1.0
    groups = list(complete.groupby("c", sort=True)) if spec.color else [(None, complete)]
    if len(groups) > 10:
        ctx.notes.append(
            f"{len(groups)} colour groups are hard to tell apart; consider fewer values"
        )
    series: list[dict[str, Any]] = []
    for name, part in groups:
        data: list[Any] = []
        for row in part.itertuples(index=False):
            point = [row.x, row.y] + ([row.s] if size else [])
            if size:
                data.append({"value": point, "symbolSize": _bubble(num(row.s) or 0.0, biggest)})
            else:
                data.append(point)
        color = ctx.colors.palette[0] if name is None else ctx.colors.color(str(name))
        s: dict[str, Any] = {"type": "scatter", "name": str(name if name is not None else y), "data": data,
                             "symbolSize": 7, "itemStyle": {"color": color, "opacity": 0.75}}  # fmt: skip
        if len(data) > LARGE_MODE and not size:
            s["large"] = True
        series.append(s)
    fields = [(x, 0, ctx.js(mx, "full")), (y, 1, ctx.js(my, "full"))]
    if ms is not None and size:
        fields.append((size, 2, ctx.js(ms, "full")))
        ctx.decisions.append(f"circle area grows with {size}")
    option = _cartesian(ctx, mx, my, series, legend=spec.color is not None)
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": fields_tooltip(fields)}})
    ctx.describe_format([mx, my], "")
    ctx.facts.update(categories=len(complete), series=len(series), rows=len(complete), x_time=False,
                     negative=bool((complete[["x", "y"]] < 0).any().any()))  # fmt: skip
    from tabsight.charts import _pretty

    title = f"{_pretty(y)} vs {_pretty(x)}" + (f" by {_pretty(spec.color)}" if spec.color else "")
    _pane(
        option,
        ctx,
        complete["x"].to_numpy(dtype="float64"),
        complete["y"].to_numpy(dtype="float64"),
    )
    return figure(ctx, title, option, height or 460)


def _grouped_scatter(frame: pd.DataFrame, ctx: _Context, height: int | None, x: str) -> Figure:
    spec = ctx.spec
    measures = ctx.measures()
    need = 3 if spec.kind == "bubble" else 2
    if len(measures) != need:
        raise InvalidSpecError(
            f"a {spec.kind} by {safe_repr(x)} needs y= with {need} measures "
            f"({'x, y and size' if need == 3 else 'one across, one up'})"
        )
    dims = [x] + ([spec.color] if spec.color else [])
    result = aggregate(frame, dims, measures, prof=ctx.prof, missing="connect")
    ctx.notes.extend(result.notes)
    vals = result.values
    mx, my = measures[0], measures[1]
    biggest = (
        max((abs(num(v) or 0) for v in vals[measures[2].label]), default=1.0) if need == 3 else 1.0
    )
    vals = _unknown_as_text(vals, [x] + ([spec.color] if spec.color else []))
    groups = (
        list(vals.groupby(spec.color, sort=True, observed=True)) if spec.color else [(None, vals)]
    )
    series: list[dict[str, Any]] = []
    for name, part in groups:
        data: list[dict[str, Any]] = []
        for _, row in part.iterrows():
            point = [num(row[m.label]) for m in measures]
            if point[0] is None or point[1] is None:
                continue
            item: dict[str, Any] = {"name": str(row[x]), "value": point}
            if need == 3:
                item["symbolSize"] = _bubble(point[2] or 0, biggest or 1.0)
            data.append(item)
        color = ctx.colors.palette[0] if name is None else ctx.colors.color(str(name))
        s = {"type": "scatter", "name": str(name) if name is not None else x, "data": data,
             "symbolSize": 9, "itemStyle": {"color": color, "opacity": 0.8}}  # fmt: skip
        if len(vals) <= 20:  # few dots: name them
            s["label"] = {"show": True, "formatter": "{b}", "position": "right", "fontSize": 10,
                          "color": ctx.theme.text_secondary}  # fmt: skip
        series.append(s)
    ctx.decisions.append(f"one dot per {x}: {mx.label} across, {my.label} up")
    if need == 3:
        ctx.decisions.append(f"circle area grows with {measures[2].label}")
    fields = [(ctx.measure_title(m), i, ctx.js(m, "full")) for i, m in enumerate(measures)]
    option = _cartesian(ctx, mx, my, series, legend=spec.color is not None)
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": fields_tooltip(fields)}})
    ctx.describe_format(measures, "")
    n = sum(len(s["data"]) for s in series)
    ctx.facts.update(categories=n, series=len(series), rows=n, x_time=False, negative=False)
    from tabsight.charts import _pretty

    title = f"{_pretty(my.label)} vs {_pretty(mx.label)} by {_pretty(x)}"
    points = np.array([d["value"][:2] for s in series for d in s["data"]], dtype="float64").reshape(
        -1, 2
    )
    _pane(option, ctx, points[:, 0], points[:, 1])
    return figure(ctx, title, option, height or 460)


def _bubble(value: float, biggest: float) -> float:
    return round(6 + 34 * math.sqrt(abs(value) / (biggest or 1.0)), 1)


def _cartesian(
    ctx: _Context, mx: Measure, my: Measure, series: list[dict[str, Any]], *, legend: bool
) -> dict[str, Any]:
    option = _build._base(ctx)
    xa = _build._value_axis(ctx.js(mx, "compact"), ctx, scale=True)
    xa.update({"name": mx.label, "nameLocation": "middle", "nameGap": 28,
               "nameTextStyle": {"color": ctx.theme.text_secondary}, "splitLine": {"show": False}})  # fmt: skip
    ya = _build._value_axis(ctx.js(my, "compact"), ctx, scale=True)
    ya.update(
        {"name": my.label, "nameTextStyle": {"color": ctx.theme.text_secondary, "align": "left"}}
    )
    option["xAxis"], option["yAxis"], option["series"] = xa, ya, series
    option["grid"] = {
        "left": 8,
        "right": 24,
        "top": 58 if legend else 30,  # room for the legend and, under it, the y-axis name
        "bottom": 30,
        "containLabel": True,
    }
    if legend:
        option["legend"] = _build._legend(ctx)
    return option


# ---------------------------------------------------------------- histogram


def histogram(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    spec = ctx.spec
    column = spec.x if isinstance(spec.x, str) else spec.y if isinstance(spec.y, str) else None
    if column is None:
        raise InvalidSpecError("a histogram needs x=<number column>")
    mx = _measure_for(ctx, column)
    values = _numbers(frame, column)
    finite = values[np.isfinite(values)]
    if finite.empty:
        raise InvalidSpecError(f"{safe_repr(column)} has no numbers to count")
    edges, why = _bins(finite, spec.options.get("bins"), spec.options.get("bin_width"))
    ctx.decisions.append(why)
    counts, _ = np.histogram(finite.to_numpy(), bins=edges)
    ranges = [
        f"{ctx.fmt(lo, mx, 'compact')} to {ctx.fmt(hi, mx, 'compact')}"
        for lo, hi in itertools.pairwise(edges)
    ]
    labels = [
        ctx.fmt(lo, mx, "compact") for lo in edges[:-1]
    ]  # where each bar starts; the tooltip has the range
    missing = len(values) - len(finite)
    if missing:
        ctx.notes.append(f"{missing:,} row(s) without a number in {column} are not counted")
    option = _build._base(ctx)
    count = Measure(None, "count")
    data = [{"value": int(c), "note": lo_hi} for c, lo_hi in zip(counts, ranges, strict=True)]
    option["series"] = [{"type": "bar", "name": "Rows", "data": data, "barCategoryGap": "2%",
                         "itemStyle": {"color": ctx.colors.palette[0]}}]  # fmt: skip
    option["xAxis"] = _build._category_axis(labels, ctx, horizontal=False, gap=True)
    option["yAxis"] = _build._value_axis(ctx.js(count, "compact"), ctx)
    option["grid"] = {"left": 8, "right": 24, "top": 20, "bottom": 8, "containLabel": True}
    option["tooltip"].update(
        {"trigger": "item", "formatter": {"$tooltip": item_tooltip(ctx, count)}}
    )
    ctx.decisions.append(
        "each bar counts the rows whose value falls in its range (lower end included)"
    )
    ctx.facts.update(categories=len(labels), series=1, rows=len(finite), x_time=False, negative=False,
                     x_ordered=True, bin_width=float(edges[1] - edges[0]))  # fmt: skip
    from tabsight.charts import _pretty

    return figure(ctx, f"Distribution of {_pretty(column)}", option, height or 420)


def _bins(
    values: pd.Series, asked: int | None, width_asked: float | None = None
) -> tuple[np.ndarray, str]:
    lo, hi = float(values.min()), float(values.max())
    n = len(values)
    if width_asked is not None:
        if width_asked <= 0 or (hi - lo) / width_asked > 1000:
            raise InvalidSpecError("bin_width must be positive and give at most 1,000 bars")
        width = float(width_asked)
        why = "bar width as asked"
    elif hi == lo:
        return np.array([lo - 0.5, lo + 0.5]), "every value is the same, so there is one bar"
    elif asked:
        width = _nearest_nice((hi - lo), asked)
        why = f"about {asked} bars, as asked, with a round bar width"
    else:
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        width = (
            2 * iqr / n ** (1 / 3) if iqr > 0 else (hi - lo) / max(1, math.ceil(math.log2(n) + 1))
        )
        count = (hi - lo) / width
        if count > MAX_BINS:
            width = (hi - lo) / MAX_BINS
        elif count < 5:
            width = (hi - lo) / 5
        width = _nice(width)
        why = (
            "bar width from the spread of the middle half of the data (Freedman-Diaconis), rounded"
        )
    start = math.floor(lo / width) * width
    stop = math.ceil(hi / width) * width
    if stop <= hi:
        stop += width
    edges = np.arange(start, stop + width / 2, width)
    return edges, f"{why}: {len(edges) - 1} bars"


def _nearest_nice(span: float, bars: int) -> float:
    """The round width (1, 2, 2.5 or 5 times a power of ten) whose bar count is closest to ``bars``."""
    raw = span / bars
    power = 10.0 ** math.floor(math.log10(raw))
    candidates = [step * power * scale for scale in (0.1, 1, 10) for step in (1, 2, 2.5, 5)]
    return min(candidates, key=lambda w: (abs(span / w - bars), w))


def _nice(width: float) -> float:
    power = 10.0 ** math.floor(math.log10(width))
    for step in (1, 2, 2.5, 5, 10):
        if step * power >= width:
            return step * power
    return 10 * power


# ---------------------------------------------------------------- box plot


def boxplot(frame: pd.DataFrame, ctx: _Context, height: int | None) -> Figure:
    spec = ctx.spec
    column = spec.y if isinstance(spec.y, str) else None
    if column is None:
        raise InvalidSpecError("a box plot needs y=<number column> (and x= to compare groups)")
    m = _measure_for(ctx, column)
    group = spec.x if isinstance(spec.x, str) else None
    values = _numbers(frame, column)
    if group is not None:
        if group not in ctx.prof:
            from tabsight.charts import _missing

            raise _missing(group, ctx.prof)
        keys = frame[group].astype("object").where(frame[group].notna(), "Unknown").astype(str)
    else:
        keys = pd.Series(column, index=frame.index)
    work = pd.DataFrame({"k": keys, "v": values}).dropna()
    sizes = work.groupby("k", sort=False)["v"].size()
    order = list(sizes.sort_values(ascending=False, kind="stable").index)
    if len(order) > MAX_BOXES:
        ctx.notes.append(f"showing the {MAX_BOXES} largest of {len(order)} groups")
        order = order[:MAX_BOXES]
    stats = []
    outliers: list[list[Any]] = []
    for i, k in enumerate(order):
        v = work.loc[work["k"] == k, "v"]
        q1, med, q3 = (float(x) for x in np.percentile(v, [25, 50, 75]))
        iqr = q3 - q1
        lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inside = v[(v >= lo_fence) & (v <= hi_fence)]
        low, high = float(inside.min()), float(inside.max())
        stats.append((k, [low, q1, med, q3, high], len(v)))
        out = v[(v < lo_fence) | (v > hi_fence)]
        outliers += [[i, float(o)] for o in out.iloc[:200]]
    if group is not None and ctx.prof[group].ordered:
        rank = {v: i for i, v in enumerate(ctx.prof[group].ordered or ())}
        stats.sort(
            key=lambda s: rank.get(s[0], len(rank))
        )  # the column's own order (Low, Medium, High)
    elif group is not None:
        stats.sort(key=lambda s: -s[1][2])
    labels = [s[0] for s in stats]
    position = {k: i for i, k in enumerate(labels)}
    outliers = [[position[order[i]], v] for i, v in outliers]
    option = _build._base(ctx)
    fmt = ctx.js(m, "full")
    option["series"] = [
        {"type": "boxplot", "name": column, "data": [{"value": s[1], "note": f"{s[2]:,} rows"} for s in stats],
         "itemStyle": {"color": ctx.theme.tile, "borderColor": ctx.colors.palette[0], "borderWidth": 1.5}},
        {"type": "scatter", "name": "Outliers", "data": outliers, "symbolSize": 5,
         "itemStyle": {"color": ctx.colors.palette[0], "opacity": 0.5}},
    ]  # fmt: skip
    option["xAxis"] = _build._category_axis(labels, ctx, horizontal=False, gap=True)
    option["yAxis"] = _build._value_axis(ctx.js(m, "compact"), ctx, scale=True)
    option["grid"] = {"left": 8, "right": 24, "top": 20, "bottom": 8, "containLabel": True}
    names = ["Lowest (within 1.5 IQR)", "Upper quartile", "Median", "Lower quartile"]
    fields = [(names[0], 0, fmt), (names[3], 1, fmt), (names[2], 2, fmt), (names[1], 3, fmt),
              ("Highest (within 1.5 IQR)", 4, fmt)]  # fmt: skip
    option["tooltip"].update({"trigger": "item", "formatter": {"$tooltip": fields_tooltip(fields)}})
    ctx.decisions.append(
        "boxes span the middle half of the values with a line at the median; whiskers reach the furthest "
        "values within 1.5 times the box height; dots beyond them are outliers"
    )
    if group is not None:
        ctx.decisions.append(f"{group} groups are sorted by median" if not ctx.prof[group].ordered
                             else f"{group} keeps its own order")  # fmt: skip
    ctx.describe_format([m], "")
    ctx.facts.update(categories=len(labels), series=1, rows=len(work), x_time=False, negative=False)
    from tabsight.charts import _pretty

    title = f"Distribution of {_pretty(column)}" + (f" by {_pretty(group)}" if group else "")
    return figure(ctx, title, option, height or 440)


# ---------------------------------------------------------------- lines over a number


def _pane(option: dict[str, Any], ctx: _Context, xs: np.ndarray, ys: np.ndarray) -> None:
    from tabsight.charts import pane

    if pane.asked(ctx):
        pane.apply_points(option, ctx, kind=ctx.spec.kind, xs=xs, ys=ys)


def numeric_lines(frame: pd.DataFrame, ctx: _Context, height: int | None, x: str) -> Figure:
    """Line or area over a number column on a real value axis (a curve, not category labels)."""
    spec = ctx.spec
    kind = spec.kind
    measures = ctx.measures()
    mx = _measure_for(ctx, x)
    work = frame.assign(**{x: _numbers(frame, x)})
    work = work[np.isfinite(work[x])]
    dims = [x] + ([spec.color] if spec.color else [])
    result = aggregate(work, dims, measures, prof=None, missing="connect")
    vals = result.values.sort_values(x, kind="stable")
    series: list[dict[str, Any]] = []
    thinned = False
    vals = _unknown_as_text(vals, [spec.color] if spec.color else [])
    groups = (
        list(vals.groupby(spec.color, sort=True, observed=True)) if spec.color else [(None, vals)]
    )
    for name, part in groups:
        for m in measures:
            pts = [[float(a), num(b)] for a, b in zip(part[x], part[m.label], strict=True)]
            if len(pts) > MAX_LINE_POINTS:
                pts = lttb(pts, MAX_LINE_POINTS)
                thinned = True
            label = str(name) if name is not None else m.label
            color = (
                ctx.colors.palette[0]
                if len(groups) * len(measures) == 1
                else ctx.colors.color(label)
            )
            s: dict[str, Any] = {"type": "line", "name": label, "data": pts, "smooth": False, "connectNulls": False,
                                 "showSymbol": len(pts) <= 40, "symbolSize": 5,
                                 "lineStyle": {"width": 2, "color": color}, "itemStyle": {"color": color}}  # fmt: skip
            if kind in ("area", "stacked_area"):
                s["areaStyle"] = {"opacity": 0.18, "color": color}
            series.append(s)
    if thinned:
        ctx.notes.append(
            f"lines thinned to {MAX_LINE_POINTS:,} points each with LTTB, which keeps their shape"
        )
    option = _cartesian(ctx, mx, measures[0], series, legend=len(series) > 1)
    option["yAxis"]["scale"] = kind not in ("area", "stacked_area")
    option["tooltip"].update({"trigger": "axis", "axisPointer": {"type": "line"},
                              "formatter": {"$tooltip": {"trigger": "axis", "fmt": ctx.js(measures[0], "full"),
                                                         "series_fmt": {s["name"]: ctx.js(measures[0], "full") for s in series},
                                                         "x_fmt": ctx.js(mx, "full")}}})  # fmt: skip
    ctx.decisions.append(
        f"{x} is a number, so it runs along a real number axis (evenly spaced by value)"
    )
    ctx.decisions.append("lines are straight between real data points, never smoothed")
    ctx.describe_format(measures, "")
    ctx.facts.update(x_time=False, x_ordered=True, categories=len(vals), series=len(series),
                     negative=bool((pd.to_numeric(vals[measures[0].label], errors="coerce") < 0).any()),
                     rows=len(vals))  # fmt: skip
    points = np.array([p for s in series for p in s["data"]], dtype="float64").reshape(-1, 2)
    _pane(option, ctx, points[:, 0], points[:, 1])
    title = ctx.title(measures, [x])
    if len(vals) == len(work) and len(measures) == 1 and not spec.color and not spec.title:
        from tabsight.charts import _pretty

        title = f"{_pretty(measures[0].label)} by {_pretty(x)}"  # one row per x: nothing was summed
    return figure(ctx, title, option, height or 420, kind=kind)


def lttb(points: list[list[Any]], threshold: int) -> list[list[Any]]:
    """Largest-Triangle-Three-Buckets downsampling (Steinarsson, 2013): keeps peaks and dips."""
    n = len(points)
    if threshold >= n or threshold < 3:
        return points
    clean = [[p[0], p[1] if p[1] is not None else 0.0] for p in points]
    out = [points[0]]
    every = (n - 2) / (threshold - 2)
    a = 0
    for i in range(threshold - 2):
        start, end = int((i + 1) * every) + 1, min(int((i + 2) * every) + 1, n)
        avg_x = sum(p[0] for p in clean[start:end]) / max(1, end - start)
        avg_y = sum(p[1] for p in clean[start:end]) / max(1, end - start)
        lo, hi = int(i * every) + 1, int((i + 1) * every) + 1
        ax, ay = clean[a]
        best, best_area = lo, -1.0
        for j in range(lo, hi):
            area = abs((ax - avg_x) * (clean[j][1] - ay) - (ax - clean[j][0]) * (avg_y - ay))
            if area > best_area:
                best, best_area = j, area
        out.append(points[best])
        a = best
    out.append(points[-1])
    return out


def _unknown_as_text(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Missing category values become "Unknown", so their points are drawn, not silently dropped."""
    from tabsight.i18n import text

    out = frame.copy()
    for col in columns:
        if out[col].isna().any():
            out[col] = out[col].astype("object").where(out[col].notna(), text("unknown"))
    return out
