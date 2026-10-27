"""Small multiples: ``facet="Region"`` draws one small chart per value, in a grid.

Each panel is built by the normal chart code on its slice of the data, then the panels are
merged into one ECharts option. Like a trellis view in a BI tool, the panels share what makes
them comparable: one value scale, one category order, one colour per series, one legend.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import Measure, aggregate
from tabsight.charts._common import num
from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError, safe_repr

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["FACET_KINDS", "facet_chart"]

FACET_KINDS = (
    "bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar", "lollipop", "line", "multi_line", "area",
    "stacked_area", "scatter", "histogram", "choropleth", "symbol_map", "density_map",
)  # fmt: skip
MAX_PANELS = 12
PANEL_HEIGHT = 220
MAP_KINDS = ("choropleth", "symbol_map", "density_map")


def facet_chart(data: pd.DataFrame, kind: str, facet: str, kwargs: dict[str, Any],
                chart: Callable[..., Figure]) -> Figure:  # fmt: skip
    from tabsight.spec import ALIASES

    kind = ALIASES.get(kind, kind)
    if kind == "auto":  # decide once on all the data, then draw every panel the same way
        picked = chart(data, "auto", **kwargs)
        kind = picked.kind
        kwargs = {**kwargs, "x": picked.spec.x, "color": picked.spec.color, "geo": picked.spec.geo,
                  "y": picked.spec.y}  # fmt: skip
        if picked.spec.options.get("freq"):
            kwargs["freq"] = picked.spec.options["freq"]
    if kind not in FACET_KINDS:
        raise InvalidSpecError(
            f"facet= works with {', '.join(FACET_KINDS)}; not with {safe_repr(kind)}"
        )
    if facet not in data.columns:
        from difflib import get_close_matches

        hint = get_close_matches(facet, [str(c) for c in data.columns], n=1)
        raise InvalidSpecError(
            f"facet column {safe_repr(facet)} not found"
            + (f"; did you mean {hint[0]!r}?" if hint else "")
        )
    if facet in {kwargs.get("x"), kwargs.get("color"), kwargs.get("geo")}:
        raise InvalidSpecError("facet= must be a different column from x=, color= and geo=")

    full = chart(data, kind, **kwargs)  # the whole data: category order, colours, map, formats
    panels = _panel_values(data, facet, kwargs, full)
    total = data[facet].nunique(dropna=True)
    notes = [n for n in full.notes]
    if total > len(panels):
        notes.append(f"showing {len(panels)} of {total} {facet} panels (the largest)")
    fixed = dict(kwargs)
    fixed["colors"] = {**_series_colors(full), **(kwargs.get("colors") or {})}
    if kind in MAP_KINDS and full.maps:
        fixed.update(_same_map(full))
    if kind == "histogram":
        fixed["bin_width"] = full.facts["bin_width"]  # every panel's bars on the same grid
        fixed.pop("bins", None)
    figures = []
    for value in panels:
        subset = data[data[facet].astype("object") == value]
        try:
            figures.append((value, chart(subset, kind, **fixed)))
        except InvalidSpecError:
            continue  # a panel with nothing to draw is skipped, not fatal
    if not figures:
        raise InvalidSpecError(f"no {facet} panel has anything to draw")
    option = _merge_maps(full, figures) if kind in MAP_KINDS else _merge_cartesian(full, figures)
    rows = math.ceil(len(figures) / _columns(len(figures)))
    decisions = [
        *list(full.decisions),
        f"one small chart per {facet} ({len(figures)} panels), sharing one scale so they compare fairly",
    ]
    return Figure(
        kind=full.kind, spec=_with_facet(full, facet), title=f"{full.title}, by {facet.replace('_', ' ')}",
        subtitle=full.subtitle, option=option, locales=full.locales, theme=full.theme,
        height=rows * PANEL_HEIGHT + 40, notes=tuple(dict.fromkeys(notes)), decisions=tuple(decisions),
        facts={**full.facts, "panels": len(figures)}, maps=full.maps,
    )  # fmt: skip


def _with_facet(full: Figure, facet: str) -> Any:
    import dataclasses

    return dataclasses.replace(full.spec, facet=facet)


def _panel_values(
    data: pd.DataFrame, facet: str, kwargs: dict[str, Any], full: Figure
) -> list[Any]:
    """Up to 12 panels: time and ordered columns keep their order, others the largest first."""
    from tabsight.profile import profile

    field = profile(data[[facet]], quiet=True)[facet]
    values = list(data[facet].dropna().unique())
    if field.role == "time" or field.ordered:
        try:
            return sorted(values)[:MAX_PANELS]
        except TypeError:
            return values[:MAX_PANELS]
    y = kwargs.get("y")
    column = (
        y
        if isinstance(y, str) and y in data.columns and pd.api.types.is_numeric_dtype(data[y])
        else None
    )
    measure = Measure(column, "sum") if column else Measure(None, "count")
    sizes = aggregate(data, facet, [measure], prof=None).values
    sizes = sizes.assign(_abs=pd.to_numeric(sizes[measure.label], errors="coerce").abs())
    return list(sizes.sort_values("_abs", ascending=False, kind="stable")[facet].head(MAX_PANELS))


def _series_colors(full: Figure) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in (full.option or {}).get("series", []):
        color = (s.get("itemStyle") or {}).get("color")
        if isinstance(color, str) and isinstance(s.get("name"), str) and color.startswith("#"):
            out[s["name"]] = color
    return out


def _same_map(full: Figure) -> dict[str, Any]:
    """Every panel on the same map as the whole data (a slice could look like another layer)."""
    name = full.maps[0]["name"]  # "ts-world" or "ts-<ISO3>-<layer>"
    if name == "ts-world":
        return {"map": "world"}
    _, country, layer = name.split("-", 2)
    return {"map": country, "layer": layer}


def _columns(n: int) -> int:
    return 1 if n == 1 else 2 if n <= 4 else 3 if n <= 9 else 4


def _cells(n: int) -> list[tuple[float, float, float]]:
    """(left %, top px, width %) for each panel."""
    cols = _columns(n)
    width = 100 / cols
    return [((i % cols) * width, 46 + (i // cols) * PANEL_HEIGHT, width) for i in range(n)]


def _title(text: str, left: float, top: float, width: float, full: Figure) -> dict[str, Any]:
    return {"text": text, "left": f"{left + 1:.2f}%", "top": top - 22,
            "textStyle": {"fontSize": 12, "fontWeight": 600, "color": full.theme.text}}  # fmt: skip


def _merge_cartesian(full: Figure, figures: list[tuple[Any, Figure]]) -> dict[str, Any]:
    base = dict(full.option or {})
    cells = _cells(len(figures))
    grids: list[dict[str, Any]] = []
    xaxes: list[dict[str, Any]] = []
    yaxes: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    titles: list[dict[str, Any]] = []
    full_x, full_y = _axis(base, "xAxis"), _axis(base, "yAxis")
    cat_axis = (
        "xAxis"
        if full_x.get("type") == "category"
        else "yAxis"
        if full_y.get("type") == "category"
        else None
    )
    order = list((full_x if cat_axis == "xAxis" else full_y).get("data") or []) if cat_axis else []
    lo, hi = _value_range(figures, cat_axis)
    point_ranges = _point_ranges(figures) if cat_axis is None else None
    for i, ((value, fig), (left, top, width)) in enumerate(zip(figures, cells, strict=True)):
        opt = fig.option or {}
        grids.append({"left": f"{left + 1:.2f}%", "width": f"{width - 3:.2f}%", "top": top,
                      "height": PANEL_HEIGHT - 66, "containLabel": True})  # fmt: skip
        titles.append(_title(str(value), left, top, width, full))
        positions: dict[str, int] | None = None
        for axis_key, out in (("xAxis", xaxes), ("yAxis", yaxes)):
            axis = dict(_axis(opt, axis_key))
            axis["gridIndex"] = i
            if axis_key == cat_axis:
                positions = {str(lb): j for j, lb in enumerate(axis.get("data") or [])}
                axis["data"] = order
                axis["axisLabel"] = {**(axis.get("axisLabel") or {}), "fontSize": 9}
            elif axis.get("type") == "value" and cat_axis is not None:
                if lo is not None and lo < 0:
                    axis["min"] = lo
                if hi is not None:
                    axis["max"] = hi
            elif point_ranges is not None:  # scatter: the same x and y range in every panel
                axis["min"], axis["max"] = point_ranges[0 if axis_key == "xAxis" else 1]
                if axis_key == "yAxis":
                    axis.pop("name", None)  # the panel title sits there
            out.append(axis)
        for s in opt.get("series", []):
            s = dict(s)
            s["xAxisIndex"], s["yAxisIndex"] = i, i
            if s.get("stack"):
                s["stack"] = f"{s['stack']}-{i}"  # ECharts stacks by name across panels otherwise
            s.pop("label", None)  # numbers on every bar of every panel would be noise
            if positions is not None and isinstance(s.get("data"), list):
                aligned: list[Any] = [None] * len(order)
                own = list(positions)
                for j, item in enumerate(s["data"]):
                    label = own[j] if j < len(own) else None
                    if label is not None and label in order:
                        aligned[order.index(label)] = item
                s["data"] = aligned
            series.append(s)
    option = {
        k: v
        for k, v in base.items()
        if k not in ("xAxis", "yAxis", "series", "grid", "dataZoom", "title")
    }
    option.update(
        {"grid": grids, "xAxis": xaxes, "yAxis": yaxes, "series": series, "title": titles}
    )
    if "legend" in base:
        option["legend"] = {**base["legend"], "top": 4}
    return option


def _axis(option: dict[str, Any], key: str) -> dict[str, Any]:
    axis = option.get(key) or {}
    return dict(axis[0] if isinstance(axis, list) else axis)


def _value_range(
    figures: list[tuple[Any, Figure]], cat_axis: str | None
) -> tuple[float | None, float | None]:
    """One value scale for all panels, so a taller bar always means a bigger number."""
    if cat_axis is None:
        return None, None
    lo, hi = 0.0, None
    for _, fig in figures:
        stacks: dict[tuple[str, int], float] = {}
        for s in (fig.option or {}).get("series", []):
            for j, item in enumerate(s.get("data") or []):
                v = num(item.get("value") if isinstance(item, dict) else item)
                if v is None:
                    continue
                if s.get("stack"):
                    key = (str(s["stack"]), j)
                    stacks[key] = stacks.get(key, 0.0) + v
                    v = stacks[key]
                lo = min(lo, v)
                hi = v if hi is None else max(hi, v)
    if hi is not None:
        hi = _round_up(hi)
    return (_round_up(lo) if lo < 0 else lo), hi


def _point_ranges(
    figures: list[tuple[Any, Figure]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    xs: list[float] = []
    ys: list[float] = []
    for _, fig in figures:
        for s in (fig.option or {}).get("series", []):
            for item in s.get("data") or []:
                point = item.get("value") if isinstance(item, dict) else item
                if isinstance(point, list) and len(point) >= 2:
                    x, y = num(point[0]), num(point[1])
                    if x is not None and y is not None:
                        xs.append(x)
                        ys.append(y)
    if not xs:
        return (0.0, 1.0), (0.0, 1.0)
    return _padded(min(xs), max(xs)), _padded(min(ys), max(ys))


def _padded(lo: float, hi: float) -> tuple[float, float]:
    pad = (hi - lo) * 0.05 or 1.0
    low = lo - pad if lo < 0 else max(0.0, lo - pad) if lo - pad < 0 else lo - pad
    return (_round_down(low), _round_up(hi + pad))


def _round_down(v: float) -> float:
    return (
        -_round_up(-v)
        if v < 0
        else (0.0 if v < 1e-12 else _round_up(v) if v == 0 else _floor_nice(v))
    )


def _floor_nice(v: float) -> float:
    power = 10.0 ** math.floor(math.log10(v))
    for step in (10, 8, 6, 5, 4, 3, 2.5, 2, 1.5, 1.2, 1):
        if step * power <= v:
            return step * power
    return power


def _round_up(v: float) -> float:
    sign = -1 if v < 0 else 1
    v = abs(v)
    if v == 0:
        return 0.0
    power = 10.0 ** math.floor(math.log10(v))
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if step * power >= v:
            return sign * step * power
    return sign * 10 * power


def _merge_maps(full: Figure, figures: list[tuple[Any, Figure]]) -> dict[str, Any]:
    base = dict(full.option or {})
    cells = _cells(len(figures))
    geos: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []
    titles: list[dict[str, Any]] = []
    mapped: list[int] = []
    numbers: list[float] = []
    for i, ((value, fig), (left, top, width)) in enumerate(zip(figures, cells, strict=True)):
        opt = fig.option or {}
        geo = dict(_axis(opt, "geo"))
        geo["_box"] = [
            left,
            top,
            width,
            PANEL_HEIGHT - 30,
        ]  # placed in the browser, keeping its shape
        geo.pop("zoom", None)
        geo.pop("center", None)
        geos.append(geo)
        titles.append(_title(str(value), left, top, width, full))
        for s in opt.get("series", []):
            s = dict(s)
            s["geoIndex"] = i
            if s.get("type") == "map":
                mapped.append(len(series))
                numbers += [
                    v for v in (num(d.get("value")) for d in s.get("data", [])) if v is not None
                ]
            series.append(s)
    option = {k: v for k, v in base.items() if k not in ("geo", "series", "title", "visualMap")}
    option.update({"geo": geos, "series": series, "title": titles})
    vm = base.get("visualMap")
    if isinstance(vm, dict) and numbers:
        lo, hi = min(numbers), max(numbers)
        if lo < 0 < hi:
            bound = max(-lo, hi)
            lo, hi = -bound, bound
        fmt = (((base.get("tooltip") or {}).get("formatter") or {}).get("$tooltip") or {}).get(
            "fmt"
        )
        option["visualMap"] = {
            **vm,
            "seriesIndex": mapped,
            "min": lo,
            "max": hi if hi > lo else lo + 1,
        }
        if fmt:  # the end labels follow the shared range, formatted like the data
            option["visualMap"].pop("text", None)
            option["visualMap"].update(
                {"calculable": True, "formatter": {"$fmt": {**fmt, "style": "compact"}}}
            )
    elif isinstance(vm, dict):
        option["visualMap"] = vm
    return option
