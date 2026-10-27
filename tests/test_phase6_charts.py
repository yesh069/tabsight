"""Phase 6: advanced charts, numeric x-axis, small multiples, df.plot and df.ts."""

from __future__ import annotations

import json
import math
import re
import warnings
from typing import Any

import numpy as np
import pandas as pd
import pytest

import tabsight as ts
from tabsight.charts import DRAWN_KINDS
from tabsight.charts.relation import lttb
from tabsight.spec import CHART_KINDS
from tabsight.warnings import InvalidSpecError, TabsightWarning

from .conftest import assert_unchanged
from .test_html_security import ALLOWED_TAGS, EVIL, _parse


def series(fig: ts.Figure, i: int = 0) -> dict[str, Any]:
    assert fig.option is not None
    return dict(fig.option["series"][i])


def test_every_kind_can_be_drawn() -> None:
    assert set(DRAWN_KINDS) == set(CHART_KINDS)


# ---------------------------------------------------------------- every kind, hostile data

EVIL_ROWS = 8


def _evil() -> pd.DataFrame:
    n = EVIL_ROWS
    names = [EVIL[i % len(EVIL)] + str(i) for i in range(n)]
    return pd.DataFrame(
        {
            "Label": names,
            "Group": [EVIL[(i + 1) % len(EVIL)] for i in range(n)],
            "Sales": [float(i + 1) * 10 for i in range(n)],
            "Profit": [float(i - 3) for i in range(n)],
            "Units": list(range(1, n + 1)),
            "Day": pd.date_range("2024-01-01", periods=n, freq="D"),
            "Country": [
                "Ireland",
                "India",
                "Brazil",
                "Germany",
                "France",
                "Spain",
                "Italy",
                "Japan",
            ],
            "Dest": ["India", "Brazil", "Germany", "France", "Spain", "Italy", "Japan", "Ireland"],
        }
    )


KIND_ARGS: dict[str, dict[str, Any]] = {
    "bar": {"x": "Label", "y": "Sales"}, "hbar": {"x": "Label", "y": "Sales"},
    "grouped_bar": {"x": "Label", "y": "Sales", "color": "Group"},
    "stacked_bar": {"x": "Label", "y": "Sales", "color": "Group"},
    "stacked100_bar": {"x": "Label", "y": "Sales", "color": "Group"},
    "lollipop": {"x": "Label", "y": "Sales"}, "bullet": {"x": "Label", "y": "Sales", "goal": 50},
    "line": {"x": "Day", "y": "Sales"}, "multi_line": {"x": "Day", "y": "Sales", "color": "Group"},
    "area": {"x": "Day", "y": "Sales"}, "stacked_area": {"x": "Day", "y": "Sales", "color": "Group"},
    "combo": {"x": "Label", "y": ["Sales", "Units"]}, "sparkline": {"x": "Day", "y": "Sales"},
    "calendar_heatmap": {"x": "Day", "y": "Sales"}, "donut": {"x": "Label", "y": "Sales"},
    "treemap": {"x": ["Group", "Label"], "y": "Sales"}, "sunburst": {"x": ["Group", "Label"], "y": "Sales"},
    "waterfall": {"x": "Label", "y": "Profit"}, "funnel": {"x": "Label", "y": "Sales"},
    "pareto": {"x": "Label", "y": "Sales"}, "kpi": {"y": "Sales"}, "gauge": {"y": "Sales"},
    "table": {"x": "Label", "y": "Sales"}, "scatter": {"x": "Sales", "y": "Profit", "color": "Group"},
    "bubble": {"x": "Label", "y": ["Sales", "Profit", "Units"]},
    "heatmap": {"x": "Label", "color": "Group", "y": "Sales"}, "histogram": {"x": "Sales"},
    "boxplot": {"x": "Group", "y": "Sales"}, "sankey": {"source": "Group", "target": "Label", "y": "Sales"},
    "choropleth": {"geo": "Country", "y": "Sales"}, "symbol_map": {"geo": "Country", "y": "Sales"},
    "density_map": {"geo": "Country", "y": "Sales"},
    "flow_map": {"source": "Country", "target": "Dest", "y": "Sales"},
}  # fmt: skip


def test_kind_args_cover_every_kind() -> None:
    assert set(KIND_ARGS) == set(CHART_KINDS)


@pytest.mark.parametrize("kind", sorted(CHART_KINDS))
def test_hostile_values_stay_text_in_every_kind(kind: str) -> None:
    df = _evil()
    before = df.copy(deep=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(df, kind, title=EVIL[0], **KIND_ARGS[kind])
    assert_unchanged(before, df)
    document = fig.to_html()
    tags, handlers = _parse(document)
    assert tags <= ALLOWED_TAGS, f"{kind}: unexpected tags {tags - ALLOWED_TAGS}"
    assert not handlers, f"{kind}: event handlers {handlers}"
    data = re.search(
        r'<script type="application/json" id="ts-figure">(.*?)</script>', document, re.S
    )
    assert data is not None and "<" not in data.group(1) and ">" not in data.group(1)
    assert json.loads(data.group(1))["title"] == EVIL[0]
    assert fig.explain() and fig.lint() is not None


# ---------------------------------------------------------------- relationship and distribution


def test_numeric_x_is_a_real_axis() -> None:
    x = np.arange(0, math.pi * 2, 0.05)
    df = pd.DataFrame({"angle": x, "sine": np.sin(x)})
    fig = ts.chart(df, "line", x="angle", y="sine")
    assert fig.option["xAxis"]["type"] == "value"  # type: ignore[index]
    pts = series(fig)["data"]
    assert len(pts) == len(x) and pts[0] == [0.0, 0.0]
    assert fig.title == "sine by angle"  # one row per angle: nothing was summed
    assert "real number axis" in fig.explain()
    big = pd.DataFrame({"t": np.arange(10_000.0), "v": np.sin(np.arange(10_000.0) / 300)})
    thinned = ts.chart(big, "line", x="t", y="v")
    assert len(series(thinned)["data"]) == 2000 and any("LTTB" in n for n in thinned.notes)


def test_lttb_keeps_ends_and_peaks() -> None:
    pts = [[float(i), 0.0] for i in range(1000)]
    pts[500][1] = 100.0
    out = lttb(pts, 50)
    assert len(out) == 50 and out[0] == pts[0] and out[-1] == pts[-1]
    assert [500.0, 100.0] in out


def test_scatter_rows_sampling_and_bubbles(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "scatter", x="Sales", y="Profit", color="Segment")
    assert {s["name"] for s in fig.option["series"]} == set(store["Segment"])  # type: ignore[index]
    many = pd.DataFrame({"a": np.arange(12_000.0), "b": np.arange(12_000.0) % 7})
    sampled = ts.chart(many, "scatter", x="a", y="b")
    assert len(series(sampled)["data"]) == 5000 and series(sampled)["large"] is True
    assert any("even sample" in n for n in sampled.notes)
    bubble = ts.chart(store, "bubble", x="Region", y=["Sales", "Profit", "Quantity"])
    sizes = [d["symbolSize"] for d in series(bubble)["data"]]
    assert max(sizes) == 40.0 and min(sizes) >= 6
    with pytest.raises(InvalidSpecError, match="needs y= with 3 measures"):
        ts.chart(store, "bubble", x="Region", y=["Sales", "Profit"])


def test_histogram_bins() -> None:
    df = pd.DataFrame({"v": np.r_[np.zeros(10), np.arange(100.0)]})
    fig = ts.chart(df, "histogram", x="v", bin_width=25)
    counts = [d["value"] for d in series(fig)["data"]]
    assert counts == [35, 25, 25, 25] and sum(counts) == len(df)
    auto = ts.chart(df, "histogram", x="v")
    assert 5 <= len(series(auto)["data"]) <= 30
    with pytest.raises(InvalidSpecError, match="bin_width"):
        ts.chart(df, "histogram", x="v", bin_width=-1)


def test_boxplot_matches_numpy() -> None:
    values = np.r_[np.arange(1.0, 21.0), 100.0]
    fig = ts.chart(pd.DataFrame({"v": values}), "boxplot", y="v")
    low, q1, med, q3, high = series(fig)["data"][0]["value"]
    assert (q1, med, q3) == tuple(np.percentile(values, [25, 50, 75]))
    assert high == 20.0 and low == 1.0  # 100 is beyond 1.5 IQR
    assert series(fig, 1)["data"] == [[0, 100.0]]


# ---------------------------------------------------------------- part-to-whole and ranking


def test_waterfall_running_totals() -> None:
    df = pd.DataFrame(
        {"Step": ["Start", "Cost", "Grant", "Tax"], "Amount": [100.0, -150.0, 30.0, -5.0]}
    )
    fig = ts.chart(df, "waterfall", x="Step", y="Amount")
    rows = [d["value"] for d in series(fig)["data"]]
    assert [r[1:3] for r in rows] == [[0, 100], [100, -50], [-50, -20], [-20, -25], [0.0, -25]]
    assert series(fig)["renderItem"] == {"$render": "range"}
    assert "steps keep the order they appear" in fig.explain()


def test_pareto_funnel_and_tree(store: pd.DataFrame) -> None:
    pareto = ts.chart(store, "pareto", x="Sub_Category", y="Sales")
    running = series(pareto, 1)["data"]
    assert running == sorted(running) and running[-1] == pytest.approx(1.0)
    stages = pd.DataFrame({"Stage": ["Visit", "Sign up", "Pay"], "Users": [1000, 250, 50]})
    funnel = ts.chart(stages, "funnel", x="Stage", y="Users")
    notes = [d.get("note") for d in series(funnel)["data"]]
    assert notes == [
        None,
        "25% of the previous stage; 25% of the first",
        "20% of the previous stage; 5% of the first",
    ]
    tree = ts.chart(store, "treemap", x=["Category", "Sub_Category"], y="Sales")
    top = series(tree)["data"]
    assert sum(d["value"] for d in top) == pytest.approx(store["Sales"].sum())
    with pytest.raises(InvalidSpecError, match="doesn't add up"):
        ts.chart(store, "treemap", x="Category", y="Discount")


# ---------------------------------------------------------------- extras and grids


def test_bullet_gauge_combo(store: pd.DataFrame) -> None:
    reps = pd.DataFrame({"Rep": ["A", "B"], "Sales": [120.0, 80.0], "Target": [100.0, 100.0]})
    bullet = ts.chart(reps, "bullet", x="Rep", y="Sales", goal="Target")
    assert [d["note"] for d in series(bullet, 1)["data"]] == [
        "goal $100.00 (120% of it)",
        "goal $100.00 (80% of it)",
    ]
    with pytest.raises(InvalidSpecError, match="goal="):
        ts.chart(reps, "bullet", x="Rep", y="Sales")
    gauge = ts.chart(reps, "gauge", y="Sales", goal=400)
    assert series(gauge)["max"] == 400 and series(gauge)["data"][0]["name"] == "50% of goal"
    combo = ts.chart(store, "combo", x="Region", y=["Sales", "Quantity"])
    assert len(combo.option["yAxis"]) == 2 and series(combo, 1)["yAxisIndex"] == 1  # type: ignore[index]


def test_sankey_breaks_cycles_and_heatmap_grid() -> None:
    flows = pd.DataFrame({"From": ["A", "B", "A"], "To": ["B", "A", "C"], "N": [5.0, 2.0, 1.0]})
    fig = ts.chart(flows, "sankey", source="From", target="To", y="N")
    names = [n["name"] for n in series(fig)["data"]]
    assert "→ B" in names and "→ A" in names  # a target that is also a source gets its own node
    with pytest.raises(InvalidSpecError, match="different columns"):
        ts.chart(flows, "sankey", source="From", target="From")
    grid = pd.DataFrame({"x": ["a", "a", "b"], "r": ["p", "q", "p"], "v": [1.0, 2.0, 3.0]})
    heat = ts.chart(grid, "heatmap", x="x", color="r", y="v")
    assert sorted(tuple(d["value"]) for d in series(heat)["data"]) == [
        (0, 0, 1.0),
        (0, 1, 2.0),
        (1, 0, 3.0),
    ]


def test_density_and_flow_maps() -> None:
    trade = pd.DataFrame(
        {"From": ["China", "Germany"], "To": ["United States", "France"], "V": [5.0, 1.0]}
    )
    flows = ts.chart(trade, "flow_map", source="From", target="To", y="V")
    lines = series(flows)["data"]
    assert lines[0]["name"] == "China → United States" and lines[0]["lineStyle"]["width"] == 8.0
    cities = pd.DataFrame({"City": ["Austin", "Boston", "Denver"], "Sales": [5.0, 2.0, 1.0]})
    density = ts.chart(cities, "density_map", geo="City", y="Sales")
    assert series(density)["type"] == "heatmap" and density.option["tooltip"]["show"] is False  # type: ignore[index]


# ---------------------------------------------------------------- small multiples


def test_facets_share_scale_order_and_colours(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "stacked_bar", x="Category", y="Sales", color="Segment", facet="Region")
    option = fig.option or {}
    assert len(option["grid"]) == 4
    largest_first = list(store.groupby("Region")["Sales"].sum().sort_values(ascending=False).index)
    assert [t["text"] for t in option["title"]] == largest_first
    maxima = {a["max"] for a in option["yAxis"]}
    orders = {tuple(a["data"]) for a in option["xAxis"]}
    assert len(maxima) == 1 and len(orders) == 1  # one scale, one category order
    stacks = {s["stack"] for s in option["series"]}
    assert len(stacks) == 4  # each panel stacks on its own
    colors: dict[str, set[str]] = {}
    for s in option["series"]:
        colors.setdefault(s["name"], set()).add(s["itemStyle"]["color"])
    assert all(len(c) == 1 for c in colors.values())  # same segment, same colour everywhere
    assert fig.facts["panels"] == 4 and "one small chart per Region" in fig.explain()


def test_facet_maps_histograms_and_errors(store: pd.DataFrame) -> None:
    maps = ts.chart(store, "map", geo="State", y="Sales", facet="Category")
    assert len(maps.option["geo"]) == 3 and all("_box" in g for g in maps.option["geo"])  # type: ignore[index]
    assert maps.option["visualMap"]["formatter"]["$fmt"]["style"] == "compact"  # type: ignore[index]
    hist = ts.chart(store, "histogram", x="Sales", facet="Segment")
    assert len({tuple(a["data"]) for a in hist.option["xAxis"]}) == 1  # type: ignore[index]
    with pytest.raises(InvalidSpecError, match="facet= works with"):
        ts.chart(store, "donut", x="Region", y="Sales", facet="Segment")
    with pytest.raises(InvalidSpecError, match="different column"):
        ts.chart(store, "bar", x="Region", y="Sales", facet="Region")
    many = store.assign(Group=[f"g{i % 20}" for i in range(len(store))])
    capped = ts.chart(many, "bar", x="Region", y="Sales", facet="Group")
    assert capped.facts["panels"] == 12 and any("12 of 20" in n for n in capped.notes)


# ---------------------------------------------------------------- df.plot and df.ts


@pytest.fixture
def tabsight_backend() -> Any:
    before = pd.options.plotting.backend
    pd.options.plotting.backend = "tabsight"
    yield
    pd.options.plotting.backend = before


def test_pandas_backend(store: pd.DataFrame, tabsight_backend: Any) -> None:
    assert store.plot.bar(x="Region", y="Sales").kind == "bar"
    assert store.plot.barh(x="Region", y="Sales").kind == "hbar"
    assert store["Sales"].plot.hist().kind == "histogram"
    assert store.plot.box(y="Profit", by="Category").kind == "boxplot"
    assert store.plot.scatter(x="Sales", y="Profit").kind == "scatter"
    assert store.groupby("Region")["Sales"].sum().plot.pie().kind == "donut"
    two = pd.DataFrame({"t": [1.0, 2.0, 3.0], "a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}).plot(
        x="t"
    )
    assert two.kind == "multi_line" and two.title == "a and b by t"
    with pytest.warns(TabsightWarning, match="figsize, rot"):
        store.plot.bar(x="Region", y="Sales", figsize=(8, 4), rot=45)
    with pytest.raises(InvalidSpecError, match="kde"):
        store["Sales"].plot.kde()
    with pytest.raises(InvalidSpecError, match="different units"):
        store.plot(x="Order_Date", y=["Sales", "Quantity"])
    with pytest.raises(InvalidSpecError, match="unknown arguments"):
        store.plot.bar(x="Region", y="Sales", nonsense=1)


def test_backend_without_the_entry_point(store: pd.DataFrame) -> None:
    # pandas falls back to "import tabsight" and its top-level plot function
    assert callable(ts.plot) and ts.plot(store, "bar", x="Region", y="Sales").kind == "bar"


def test_accessors(store: pd.DataFrame) -> None:
    before = store.copy(deep=True)
    assert store.ts.bar(x="Region", y="Sales").kind == "bar"
    assert store.ts.chart(x="Region", y="Sales").kind in ("bar", "hbar")  # "auto" by default
    assert store.ts.recommend(x="Region", y="Sales").best.kind == "bar"
    assert store.ts.profile()["Sales"].role == "measure"
    assert store["Profit"].ts.hist().kind == "histogram"
    assert hasattr(store.ts, "flow_map") and hasattr(store.ts, "map")
    assert_unchanged(before, store)


def test_notebook_size_tip(store: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    import tabsight.figure as figure

    monkeypatch.setattr(figure, "NOTEBOOK_TIP_BYTES", 1)
    monkeypatch.setattr(figure, "_NOTEBOOK", {"bytes": 0, "tipped": 0})
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    with pytest.warns(TabsightWarning, match="cdn=True"):
        fig._repr_html_()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig._repr_html_()  # only once
    with ts.config(cdn=True):
        assert "cdn.jsdelivr.net" in fig._repr_html_()
