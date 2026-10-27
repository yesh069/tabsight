"""A pandas plotting backend: ``df.plot(...)`` drawn by tabsight.

    pd.options.plotting.backend = "tabsight"
    df.plot(x="Order_Date", y="Sales")          # a tabsight line chart
    df.plot.bar(x="Region", y="Sales")          # bars, largest first
    df["Sales"].plot.hist()                     # a histogram

Differences from pandas' own plots, on purpose:
- tabsight aggregates: one bar per Region with the sum of Sales, not one bar per row (the
  same thing when x is already unique);
- several y columns become one chart with a series each, only when they share a unit;
- matplotlib styling arguments (``figsize``, ``ax``, ``style``...) are ignored with one warning.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from tabsight.figure import Figure
from tabsight.warnings import InvalidSpecError, TabsightWarning, safe_repr

__all__ = ["KINDS", "plot"]

# pandas kind -> (tabsight kind for one series, for several series)
KINDS: dict[str, tuple[str, str]] = {
    "line": ("line", "multi_line"),
    "bar": ("bar", "grouped_bar"),
    "barh": ("hbar", "grouped_bar"),
    "area": ("area", "stacked_area"),
    "pie": ("donut", "donut"),
    "scatter": ("scatter", "scatter"),
    "hist": ("histogram", "histogram"),
    "box": ("boxplot", "boxplot"),
}
_NOT_YET = {"kde": "histogram", "density": "histogram", "hexbin": "heatmap or density_map"}
# tabsight's own arguments, passed straight through
_OURS = {
    "agg", "sort", "top", "freq", "title", "subtitle", "unit", "currency", "decimals", "format", "theme",
    "locale", "palette", "colors", "height", "geo", "map", "level", "layer", "geo_map", "geo_names",
    "projection", "size", "goal", "bins", "facet",
}  # fmt: skip
# matplotlib styling pandas accepts; meaningless here, so ignored with one warning
_STYLING = {
    "figsize", "ax", "style", "grid", "legend", "logx", "logy", "loglog", "xlim", "ylim", "rot", "fontsize",
    "colormap", "table", "xerr", "yerr", "secondary_y", "mark_right", "include_bool", "backend", "use_index",
    "sharex", "sharey", "layout", "linewidth", "lw", "alpha", "marker", "linestyle", "xticks", "yticks",
    "xlabel", "ylabel", "position", "width", "edgecolor", "s", "c", "sort_columns", "subplots",
}  # fmt: skip


def plot(data: pd.DataFrame | pd.Series, kind: str = "line", **kwargs: Any) -> Figure:
    """Entry point pandas calls for ``df.plot(...)`` when the backend is "tabsight"."""
    from tabsight.charts import chart

    if kind in _NOT_YET:
        raise InvalidSpecError(
            f"kind={kind!r} isn't drawn by tabsight; try kind={_NOT_YET[kind]!r} with ts.chart"
        )
    if kind not in KINDS:
        raise InvalidSpecError(f"kind={safe_repr(kind)} must be one of {sorted(KINDS)}")
    kwargs = {k: v for k, v in kwargs.items() if v is not None}  # pandas sends its defaults as None
    by = kwargs.pop("by", None)
    frame, x, ys = _frame(data, kwargs.pop("x", None), kwargs.pop("y", None), kind)
    stacked = bool(kwargs.pop("stacked", False))
    color = kwargs.pop("color", None)
    if isinstance(color, str) and color in frame.columns:
        kwargs["color"] = color  # tabsight's color= is a column that splits the series
    elif color is not None:
        kwargs.setdefault("_ignored", []).append("color")
    ignored = sorted({k for k in kwargs if k in _STYLING} | set(kwargs.pop("_ignored", [])))
    unknown = sorted(k for k in kwargs if k not in _OURS and k not in _STYLING and k != "color")
    if unknown:
        raise InvalidSpecError(f"df.plot got unknown arguments {unknown}")
    if ignored:
        warnings.warn(
            f"tabsight ignores matplotlib styling: {', '.join(ignored)}",
            TabsightWarning,
            stacklevel=3,
        )
    passed = {k: v for k, v in kwargs.items() if k in _OURS or k == "color"}
    one, many = KINDS[kind]

    if by is not None and not isinstance(by, str):
        raise InvalidSpecError("by= takes one column name")
    if kind in ("hist", "box"):
        if len(ys) == 1:
            if kind == "box":
                return chart(frame, "boxplot", x=by, y=ys[0], **passed)
            return chart(frame, "histogram", x=ys[0], facet=by, **passed)
        long = _long(frame, None, ys)
        return chart(
            long,
            one,
            x="Series" if kind == "box" else "Value",
            y="Value" if kind == "box" else None,
            **passed,
        )
    if kind == "scatter":
        if x is None or len(ys) != 1:
            raise InvalidSpecError("df.plot.scatter needs x= and y= (one column each)")
        return chart(frame, "scatter", x=x, y=ys[0], **passed)
    if x is None:
        raise InvalidSpecError("no x column: pass x= or give the data a meaningful index")
    if len(ys) == 1:
        target = "stacked_bar" if stacked and "color" in passed and kind in ("bar", "barh") else one
        return chart(frame, target, x=x, y=ys[0], **passed)
    _same_unit(frame, ys)
    long = _long(frame, x, ys)
    target = "stacked_bar" if stacked and kind in ("bar", "barh") else many
    if kind == "pie":
        raise InvalidSpecError("a pie shows one column; pass y=")
    passed.setdefault("title", f"{_and(ys)} by {x.replace('_', ' ')}")
    return chart(long, target, x=x, y="Value", color="Series", **passed)


def _and(items: list[str]) -> str:
    names = [i.replace("_", " ") for i in items]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _frame(data: Any, x: Any, y: Any, kind: str) -> tuple[pd.DataFrame, str | None, list[str]]:
    if isinstance(data, pd.Series):
        name = str(data.name) if data.name is not None else "Value"
        frame = data.to_frame(name)
        ys = [name]
    elif isinstance(data, pd.DataFrame):
        frame = data
        ys = [y] if isinstance(y, str) else list(y) if y is not None else []
    else:
        raise InvalidSpecError("df.plot needs a DataFrame or a Series")
    if x is None and kind not in ("hist", "box", "pie"):
        # like pandas: no x means the index
        index_name = frame.index.name or "index"
        frame = frame.reset_index(
            names=index_name if index_name not in frame.columns else f"{index_name}_"
        )
        x = str(frame.columns[0])
    elif kind == "pie" and x is None:
        index_name = frame.index.name or "Label"
        frame = frame.reset_index(names=index_name)
        x = index_name
    if not ys:
        ys = [str(c) for c in frame.columns if c != x and pd.api.types.is_numeric_dtype(frame[c])
              and not pd.api.types.is_bool_dtype(frame[c])]  # fmt: skip
        if not ys:
            raise InvalidSpecError("no number columns to plot; pass y=")
        if len(ys) > 10:
            raise InvalidSpecError(f"{len(ys)} number columns is too many for one chart; pass y=[...] "
                                   "or try ts.chart(df, 'auto', ...)")  # fmt: skip
    for col in [c for c in [x, *ys] if c is not None]:
        if col not in frame.columns:
            raise InvalidSpecError(f"column {safe_repr(col)} not found")
    return frame, x, ys


def _same_unit(frame: pd.DataFrame, ys: list[str]) -> None:
    from tabsight.profile import profile

    prof = profile(frame[ys], quiet=True)
    units = {prof[c].unit for c in ys}
    if len(units) > 1:
        raise InvalidSpecError(
            f"{', '.join(ys)} have different units ({', '.join(sorted(u or 'none' for u in units))}), so one axis "
            "would flatten one of them; plot them separately, or use ts.chart(df, 'combo', ...)"
        )


def _long(frame: pd.DataFrame, x: str | None, ys: list[str]) -> pd.DataFrame:
    """Wide columns to long rows: one series per original column, in the given order."""
    keep = [x] if x else []
    long = frame[keep + ys].melt(
        id_vars=keep or None, value_vars=ys, var_name="Series", value_name="Value"
    )
    long["Series"] = pd.Categorical(long["Series"], categories=ys, ordered=True)
    return long
