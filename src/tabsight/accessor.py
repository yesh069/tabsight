"""``df.ts`` and ``series.ts``: tabsight from any DataFrame, without changing pandas settings.

df.ts.bar(x="Region", y="Sales")
df.ts.chart("auto", x="Order_Date", y="Sales")
df.ts.recommend(x="Sub_Category", y="Discount")
df["Sales"].ts.hist()
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from tabsight.figure import Figure

__all__ = ["DataFrameAccessor", "SeriesAccessor"]

# one method per chart kind (the alias "map" too)
_KINDS = (
    "bar", "hbar", "grouped_bar", "stacked_bar", "stacked100_bar", "lollipop", "bullet", "line", "multi_line",
    "area", "stacked_area", "combo", "sparkline", "calendar_heatmap", "donut", "treemap", "sunburst",
    "waterfall", "funnel", "pareto", "kpi", "gauge", "table", "scatter", "bubble", "heatmap", "histogram",
    "boxplot", "sankey", "map", "choropleth", "symbol_map", "density_map", "flow_map",
)  # fmt: skip


class DataFrameAccessor:
    """tabsight on a DataFrame: ``df.ts.chart(...)``, ``df.ts.bar(...)``, ``df.ts.profile()``..."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def chart(self, kind: str = "auto", **kwargs: Any) -> Figure:
        """``ts.chart(df, kind, ...)``; the default kind is "auto"."""
        from tabsight.charts import chart

        return chart(self._frame, kind, **kwargs)

    def recommend(self, **kwargs: Any) -> Any:
        from tabsight.recommend import recommend

        return recommend(self._frame, **kwargs)

    def profile(self, **kwargs: Any) -> Any:
        from tabsight.profile import profile

        return profile(self._frame, **kwargs)

    def check(self, **kwargs: Any) -> Any:
        from tabsight.check import check

        return check(self._frame, **kwargs)

    def aggregate(self, dims: Any = None, measures: Any = None, **kwargs: Any) -> Any:
        from tabsight.aggregate import aggregate

        return aggregate(self._frame, dims, measures, **kwargs)


class SeriesAccessor:
    """tabsight on one column: ``s.ts.hist()``, ``s.ts.line()`` (over the index), ``s.ts.bar()``..."""

    def __init__(self, series: pd.Series) -> None:
        self._series = series

    def chart(self, kind: str = "line", **kwargs: Any) -> Figure:
        from tabsight.plotting import KINDS, plot

        pandas_kind = {v[0]: k for k, v in KINDS.items()}.get(kind, kind)
        if pandas_kind in KINDS:
            return plot(self._series, pandas_kind, **kwargs)
        from tabsight.charts import chart

        name = str(self._series.name) if self._series.name is not None else "Value"
        frame = self._series.to_frame(name).reset_index()
        return chart(frame, kind, x=str(frame.columns[0]), y=name, **kwargs)

    def line(self, **kwargs: Any) -> Figure:
        return self.chart("line", **kwargs)

    def bar(self, **kwargs: Any) -> Figure:
        return self.chart("bar", **kwargs)

    def hist(self, **kwargs: Any) -> Figure:
        return self.chart("histogram", **kwargs)

    def box(self, **kwargs: Any) -> Figure:
        return self.chart("boxplot", **kwargs)

    def area(self, **kwargs: Any) -> Figure:
        return self.chart("area", **kwargs)


def _make(kind: str) -> Any:
    def method(self: DataFrameAccessor, **kwargs: Any) -> Figure:
        return self.chart(kind, **kwargs)

    method.__name__ = kind
    method.__doc__ = f'``ts.chart(df, "{kind}", ...)``'
    return method


for _kind in _KINDS:
    setattr(DataFrameAccessor, _kind, _make(_kind))


def register() -> None:
    """Add ``.ts`` to every DataFrame and Series (done when tabsight is imported)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # re-registering on reload is fine
        pd.api.extensions.register_dataframe_accessor("ts")(DataFrameAccessor)
        pd.api.extensions.register_series_accessor("ts")(SeriesAccessor)
