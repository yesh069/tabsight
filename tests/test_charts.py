from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import tabsight as ts
from tabsight.warnings import InvalidSpecError

from .conftest import assert_unchanged


def series(fig: ts.Figure) -> list[dict[str, Any]]:
    assert fig.option is not None
    return list(fig.option["series"])


def test_bar_follows_the_bi_rules(store: pd.DataFrame) -> None:
    before = store.copy(deep=True)
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    assert_unchanged(before, store)
    assert fig.title == "Sum of Sales by Region"
    s = series(fig)
    assert len(s) == 1 and s[0]["type"] == "bar"
    values = s[0]["data"]
    assert values == sorted(values, reverse=True)  # rankings: largest first
    assert fig.option["xAxis"]["axisLabel"]["interval"] == 0  # every label shown
    assert fig.option["yAxis"]["axisLabel"]["formatter"]["$fmt"]["unit"] == "currency"
    assert s[0]["label"]["show"] is True  # 4 bars: values on the bars
    json.dumps(fig.to_dict())  # plain JSON


def test_long_labels_switch_to_horizontal_bars() -> None:
    df = pd.DataFrame(
        {"Product": [f"Very long product name number {i}" for i in range(6)], "Sales": range(6)}
    )
    fig = ts.chart(df, "bar", x="Product", y="Sales")
    assert fig.kind == "hbar"
    assert fig.option["yAxis"]["type"] == "category" and fig.option["yAxis"]["inverse"] is True
    assert any("horizontal" in n for n in fig.notes)


def test_stacked_grouped_and_100_percent(store: pd.DataFrame) -> None:
    stacked = ts.chart(store, "stacked_bar", x="Category", y="Sales", color="Region")
    assert {s["stack"] for s in series(stacked)} == {"total"}
    assert "legend" in stacked.option
    grouped = ts.chart(store, "grouped_bar", x="Category", y="Sales", color="Region")
    assert all("stack" not in s for s in series(grouped))
    pct = ts.chart(store, "stacked100_bar", x="Region", y="Sales", color="Segment")
    columns = list(zip(*[s["data"] for s in series(pct)], strict=True))
    assert all(abs(sum(v for v in col if v) - 1) < 1e-9 for col in columns)
    assert pct.option["yAxis"]["axisLabel"]["formatter"]["$fmt"]["unit"] == "percent"


def test_same_value_same_colour_across_charts(store: pd.DataFrame) -> None:
    a = ts.chart(store, "stacked_bar", x="Category", y="Sales", color="Region")
    b = ts.chart(store, "multi_line", x="Order_Date", y="Sales", color="Region", freq="quarter")
    colours_a = {s["name"]: s["itemStyle"]["color"] for s in series(a)}
    colours_b = {s["name"]: s["itemStyle"]["color"] for s in series(b)}
    assert colours_a == colours_b
    pinned = ts.chart(
        store, "stacked_bar", x="Category", y="Sales", color="Region", colors={"West": "#000000"}
    )
    assert {s["name"]: s["itemStyle"]["color"] for s in series(pinned)}["West"] == "#000000"


def test_lines_are_never_smoothed_and_gaps_stay_gaps(store: pd.DataFrame) -> None:
    for kind in ("line", "area", "multi_line", "stacked_area", "sparkline"):
        kw = {"color": "Region"} if kind in ("multi_line", "stacked_area") else {}
        fig = ts.chart(store, kind, x="Order_Date", y="Sales", freq="month", **kw)
        assert all(s["smooth"] is False and s["connectNulls"] is False for s in series(fig)), kind
    line = ts.chart(store, "line", x="Order_Date", y="Sales", freq="month")
    assert line.option["yAxis"]["scale"] is True  # lines need not start at zero
    assert (
        ts.chart(store, "area", x="Order_Date", y="Sales", freq="month").option["yAxis"]["scale"]
        is False
    )


def test_incomplete_last_period_is_called_out() -> None:
    df = pd.DataFrame(
        {"d": pd.to_datetime(["2017-01-10", "2017-02-10", "2017-03-01"]), "v": [5.0, 6.0, 1.0]}
    )
    fig = ts.chart(df, "line", x="d", y="v", freq="month")
    assert any("incomplete" in n for n in fig.notes)


def test_donut_keeps_seven_slices_plus_other(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "donut", x="Sub_Category", y="Sales")
    data = series(fig)[0]["data"]
    assert len(data) == 8 and data[-1]["name"].startswith("Other (")
    assert data[-1]["itemStyle"]["color"] == "#bab0ac"
    assert series(fig)[0]["startAngle"] == 90


def test_donut_with_negative_values_falls_back_to_bars() -> None:
    df = pd.DataFrame({"g": ["a", "b", "c"], "v": [5.0, -2.0, 3.0]})
    fig = ts.chart(df, "donut", x="g", y="v")
    assert fig.kind == "hbar"


def test_kpi_and_table(store: pd.DataFrame) -> None:
    kpi = ts.chart(store, "kpi", y="Sales")
    assert kpi.kpi is not None and kpi.option is None
    assert kpi.kpi["value_text"].startswith("$") and kpi.title == "Sum of Sales"
    table = ts.chart(store, "table", x=["Category", "Sub_Category"], y=["Sales", "Discount"])
    assert table.table is not None
    assert [c["name"] for c in table.table["columns"]] == [
        "Category",
        "Sub Category",
        "Sum of Sales",
        "Avg Discount",
    ]
    first_category = [row[0] for row in table.table["rows"]]
    assert first_category.count("") > 0  # repeated parents are blanked
    assert all(row[3].endswith("%") and "." in row[3] for row in table.table["rows"])


def test_text_measures_are_counted(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "bar", x="Region", y="Order_ID")
    assert fig.title == "Distinct Order ID by Region"
    assert fig.option["yAxis"]["axisLabel"]["formatter"]["$fmt"]["unit"] == "count"


def test_clear_errors(store: pd.DataFrame) -> None:
    with pytest.raises(InvalidSpecError, match="phase 5"):
        ts.chart(store, "map", x="State", y="Sales")
    with pytest.raises(InvalidSpecError, match="needs x="):
        ts.chart(store, "bar", y="Sales")
    with pytest.raises(InvalidSpecError, match="needs y="):
        ts.chart(store, "bar", x="Region")
    with pytest.raises(InvalidSpecError, match="did you mean 'Sales'"):
        ts.chart(store, "bar", x="Region", y="sales")
    with pytest.raises(InvalidSpecError, match="needs color="):
        ts.chart(store, "stacked_bar", x="Region", y="Sales")
    with pytest.raises(InvalidSpecError):
        ts.chart(store, "bar", x="Region", y="Sales", height=10)


def test_html_file_is_written_and_self_contained(store: pd.DataFrame, tmp_path: Path) -> None:
    path = tmp_path / "chart.html"
    document = ts.chart(store, "line", x="Order_Date", y="Sales", freq="month").to_html(path)
    assert path.read_text(encoding="utf-8") == document
    assert "http://" not in document.split("<script", 1)[0]
    assert ts.ECHARTS_VERSION in document and "tabsight.render" in document


def test_runtime_js_is_available() -> None:
    runtime = ts.runtime_js()
    assert "root.tabsight = {" in runtime and "render: render," in runtime
