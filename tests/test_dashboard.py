"""Phase 8: dashboards. The browser must give the same numbers as Python after any filter."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

import tabsight as ts
from tabsight.aggregate import _time_values, bucket
from tabsight.profile import _prepare, profile
from tabsight.warnings import InvalidSpecError

from .conftest import assert_unchanged, superstore_like
from .test_html_security import EVIL, _parse

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "tabsight" / "render" / "static"
SCRIPT = ROOT / "tests" / "js" / "dashboard_parity.cjs"
DASH = chr(0x2013)  # the en dash between months

TILES: list[dict[str, Any]] = [
    {"kind": "kpi", "y": "Sales"},
    {"kind": "kpi", "y": "Discount"},
    {"kind": "kpi", "y": "Sales", "compare": "previous_year"},
    {"kind": "bar", "x": "Region", "y": "Sales"},
    {"kind": "hbar", "x": "Sub_Category", "y": "Profit", "top": 6},
    {"kind": "line", "x": "Order_Date", "y": "Sales", "freq": "month"},
    {"kind": "multi_line", "x": "Order_Date", "y": "Sales", "color": "Category", "freq": "quarter"},
    {"kind": "stacked_bar", "x": "Region", "y": "Sales", "color": "Segment"},
    {"kind": "stacked100_bar", "x": "Category", "y": "Quantity", "color": "Region"},
    {"kind": "grouped_bar", "x": "Category", "y": "Discount", "color": "Segment"},
    {"kind": "donut", "x": "Segment", "y": "Sales"},
    {"kind": "bar", "x": "Category", "y": ["Sales", "Profit"]},
    {"kind": "map", "geo": "State", "y": "Sales"},
    {"kind": "table", "x": ["Region", "Category"], "y": ["Sales", "Discount"]},
    {"kind": "area", "x": "Order_Date", "y": "Profit", "freq": "year"},
]


@pytest.fixture(scope="module")
def orders() -> pd.DataFrame:
    df = superstore_like(900, seed=11)
    df.loc[::37, "Segment"] = None  # missing values become "Unknown" in both languages
    return df


def _dash(orders: pd.DataFrame) -> ts.Dashboard:
    dash = ts.Dashboard("Sales", data=orders, filters=["Region", "Order_Date", "Segment"])
    for tile in TILES:
        dash.add(**tile)
    return dash


def _month(frame: pd.DataFrame) -> pd.Series:
    frame, _ = _prepare(frame)
    prof = profile(frame, quiet=True)
    return bucket(_time_values(frame["Order_Date"], prof, "Order_Date"), "month").dt.strftime(
        "%Y-%m-%d"
    )


def _apply(frame: pd.DataFrame, filters: dict[str, Any], skip: str | None = None) -> pd.DataFrame:
    keep = pd.Series(True, index=frame.index)
    for col, f in filters.items():
        if skip is not None and f.get("source") == skip:
            continue
        if f["type"] == "range":
            month = _month(frame)
            keep &= (month >= f["lo"]) & (month <= f["hi"])
        else:
            values = frame[col].map(lambda v: None if pd.isna(v) else str(v))
            keep &= values.isin([v for v in f["values"] if v is not None]) | (
                values.isna() & (None in f["values"])
            )
    return frame[keep]


def _summary(fig: ts.Figure, tile: dict[str, Any]) -> dict[str, Any]:
    if fig.kind == "kpi":
        return {"kpi": fig.kpi}
    if fig.kind == "table":
        return {"rows": fig.table["rows"]}  # type: ignore[index]
    opt = fig.option or {}
    if fig.kind == "choropleth":
        return {"map": {d["name"]: d["value"] for d in opt["series"][0]["data"]}}
    if fig.kind == "donut":
        data = opt["series"][0]["data"]
        return {
            "labels": [d["name"] for d in data],
            "series": {tile["y"]: [d["value"] for d in data]},
        }
    cat = opt["yAxis"] if fig.kind == "hbar" else opt["xAxis"]
    series = {}
    for s in opt["series"]:
        series[s["name"]] = [d.get("value") if isinstance(d, dict) else d for d in s["data"]]
    return {"labels": cat["data"], "series": series}


def _close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return (a in (None, 0)) and (b in (None, 0))  # a missing bar and a zero bar look the same
    return bool(np.isclose(float(a), float(b), rtol=1e-9, atol=1e-9))


def _node(
    payload: dict[str, Any],
    filters: list[dict[str, Any]],
    tmp: Path,
    sanitize: Any = None,
    deep: list[str] | None = None,
) -> Any:
    data = tmp / "cases.json"
    cases: dict[str, Any] = {"payload": payload, "filters": filters}
    if sanitize is not None:
        cases["sanitize"] = sanitize
    if deep is not None:
        cases["deep"] = deep
    data.write_text(json.dumps(cases), encoding="utf-8")
    run = subprocess.run(
        ["node", str(SCRIPT), str(STATIC / "tabsight.js"), str(STATIC / "dashboard.js"), str(data)],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=120,
    )  # fmt: skip
    return json.loads(run.stdout)


FILTERS: list[dict[str, Any]] = [
    {},
    {"Region": {"type": "in", "values": ["West"]}},
    {"Region": {"type": "in", "values": ["East", "South"]}, "Segment": {"type": "in", "values": ["Consumer", None]}},
    {"Order_Date|month": {"type": "range", "lo": "2015-03-01", "hi": "2016-08-01"}},
    {"Sub_Category": {"type": "in", "values": ["Phones", "Chairs"], "source": "t4"}},
    {"Category": {"type": "in", "values": ["Technology"], "source": "t11"}, "Region": {"type": "in", "values": ["Central"]}},
]  # fmt: skip


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_browser_numbers_match_python_after_every_filter(
    orders: pd.DataFrame, tmp_path: Path
) -> None:
    dash = _dash(orders)
    payload = dash.build()
    live = {t["id"]: t for t in payload["tiles"] if "binding" in t}
    assert len(live) == len(TILES), [t.get("static") for t in payload["tiles"]]
    results = _node(payload, FILTERS, tmp_path)
    full_as_of = None
    for filters, tiles in zip(FILTERS, results, strict=True):
        for got in tiles:
            i = int(got["id"][1:])
            tile = dict(TILES[i])
            frame = _apply(orders, filters, skip=got["id"])
            if tile.get("compare"):
                if any(f["type"] == "range" for f in filters.values()):
                    continue  # a date filter sets the window: see the next test
                if full_as_of is None:
                    full_as_of = str(ts.compare(orders, "Sales", "Order_Date").as_of.date())
                tile["as_of"] = full_as_of  # "today" comes from all the data, not the filtered rows
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig = ts.chart(frame, tile.pop("kind"), colors=payload["colors"], **tile)
            want = _summary(fig, TILES[i])
            where = f"tile {i} {TILES[i]} with {filters}"
            if "kpi" in want:
                assert got["kpi"]["value_text"] == want["kpi"]["value_text"], where
                if TILES[i].get("compare"):
                    assert got["kpi"]["detail"] == want["kpi"]["detail"], where
            elif "rows" in want:
                assert got["rows"] == want["rows"], where
            elif "map" in want:
                assert set(got["map"]) == set(want["map"]), where
                assert all(_close(got["map"][k], v) for k, v in want["map"].items()), where
            else:
                assert got["labels"] == want["labels"], where
                assert set(got["series"]) == set(want["series"]), where
                for name, values in want["series"].items():
                    assert len(got["series"][name]) == len(values), (where, name)
                    assert all(
                        _close(a, b) for a, b in zip(got["series"][name], values, strict=True)
                    ), (where, name)


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_kpi_compares_the_filtered_months_with_the_same_months_last_year(
    orders: pd.DataFrame, tmp_path: Path
) -> None:
    dash = ts.Dashboard("KPI", data=orders, filters=["Order_Date", "Region"]).kpi(
        "Sales", compare="previous_year"
    )
    payload = dash.build()
    f = {"Order_Date|month": {"type": "range", "lo": "2016-03-01", "hi": "2016-05-01"},
         "Region": {"type": "in", "values": ["West"]}}  # fmt: skip
    got = _node(payload, [f], tmp_path)[0][0]["kpi"]
    west = orders[orders["Region"] == "West"]
    c = ts.compare(west, "Sales", "Order_Date", window=("2016-03-01", "2016-05-31"))
    assert got["detail"].startswith("Mar 2016 " + DASH + " May 2016 · ") and got["detail"].endswith(
        "vs Mar 2015 " + DASH + " May 2015"
    )
    assert f"{abs(c.pct) * 100:.1f}%" in got["detail"]
    assert got["value_text"] == ts.format_number(c.current, "currency", "compact")


# ---------------------------------------------------------------- the model and the file


def test_only_single_row_charts_stay_static(orders: pd.DataFrame) -> None:
    coords = orders.assign(
        lat=40.0 + np.arange(len(orders)) % 5, lon=-100.0 + np.arange(len(orders)) % 7
    )
    dash = (ts.Dashboard("Mixed", data=coords).add("scatter", x="Sales", y="Profit")
            .add("symbol_map", lat="lat", lon="lon", y="Sales").add("bar", x="Region", y="Order_ID", agg="countd"))  # fmt: skip
    tiles = dash.build()["tiles"]
    assert "single rows" in tiles[0]["static"] and "single rows" in tiles[1]["static"]
    assert "binding" in tiles[2] and "static" not in tiles[2]
    codes = [c for c in dash.build()["data"]["lists"] if c.endswith("_values")]
    assert codes and all(
        isinstance(v, int) for lst in dash.build()["data"]["lists"][codes[0]] for v in lst
    )


def test_distinct_counts_never_put_the_values_in_the_page(orders: pd.DataFrame) -> None:
    page = ts.Dashboard("IDs", data=orders).add("kpi", y="Order_ID", agg="countd").to_html()
    assert orders["Order_ID"].iloc[0] not in page and orders["Order_ID"].iloc[-1] not in page


def test_shared_table_holds_parts_not_rows(orders: pd.DataFrame) -> None:
    payload = _dash(orders).build()
    data = payload["data"]
    assert data["rows"] < len(orders)
    assert (
        "Order_ID" not in data["dims"] and "Postal_Code" not in data["dims"]
    )  # never used, never stored
    assert any(
        c.endswith("_count") for c in data["nums"]
    )  # means keep their counts, so they stay exact
    assert set(data["dims"]) >= {
        "Region",
        "Order_Date|month",
        "Order_Date|quarter",
        "Segment",
        "State",
    }
    assert 0 < data["size_mb"] < 1


def test_one_colour_per_value_across_tiles(orders: pd.DataFrame) -> None:
    dash = (ts.Dashboard("Colours", data=orders).add("stacked_bar", x="Region", y="Sales", color="Segment")
            .add("donut", x="Segment", y="Sales"))  # fmt: skip
    payload = dash.build()
    bars = payload["tiles"][0]["figure"]["option"]["series"]
    donut = payload["tiles"][1]["figure"]["option"]["series"][0]["data"]
    by_name = {d["name"]: d["itemStyle"]["color"] for d in donut}
    for s in bars:
        assert by_name.get(s["name"], payload["colors"].get(s["name"])) == s["itemStyle"]["color"]


def test_save_load_and_bind_round_trip(orders: pd.DataFrame, tmp_path: Path) -> None:
    dash = _dash(orders).insights(3)
    path = tmp_path / "sales.json"
    dash.save(path)
    loaded = ts.Dashboard.load(path)
    assert loaded.to_dict() == dash.to_dict() and "data" not in json.loads(
        path.read_text(encoding="utf-8")
    )
    bound = loaded.bind(orders.head(400))
    assert bound.build()["data"]["rows"] > 0
    with pytest.raises(InvalidSpecError, match="no column 'Region'; did you mean 'Regions'"):
        loaded.bind(orders.rename(columns={"Region": "Regions"}))
    with pytest.raises(InvalidSpecError, match="no data yet"):
        loaded.build()


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"tiles": [{"kind": "bar", "onclick": "x"}]}, "unknown tile setting"),
        ({"tiles": [{"kind": "bar", "x": {"__class__": 1}}]}, None),
        ({"tiles": [{"kind": "bar", "w": 13}]}, "1-12"),
        ({"tiles": [{"kind": "bar", "action": "eval"}]}, "action"),
        ({"script": "<script>"}, "unknown dashboard key"),
        ({"tiles": [{"kind": "bar", "y": float("nan")}]}, "finite"),
        ({"tabsight_dashboard": 99}, "version"),
        ({"tiles": "bar"}, "list"),
        ([1, 2], "object"),
        ({"title": "x" * 400}, "title"),
        ({"filters": ["Region"] * 1 + [5]}, "column names"),
    ],
)
def test_untrusted_dashboard_files_are_refused(bad: Any, match: str | None) -> None:
    with pytest.raises(InvalidSpecError, match=match):
        dash = ts.Dashboard.from_dict(bad)
        dash.bind(superstore_like(50)).build()


def test_tile_arguments_are_checked(orders: pd.DataFrame) -> None:
    dash = ts.Dashboard("x", data=orders)
    with pytest.raises(InvalidSpecError, match="did you mean 'color'"):
        dash.add("bar", x="Region", y="Sales", colour="Segment")
    with pytest.raises(InvalidSpecError, match="small multiples"):
        dash.add("bar", x="Region", y="Sales", facet="Segment")
    with pytest.raises(InvalidSpecError, match="plain JSON"):
        dash.add("bar", x="Region", y=object())
    with pytest.raises(InvalidSpecError, match="not found"):
        ts.Dashboard("x", data=orders, filters=["Nope"]).add("bar", x="Region", y="Sales").build()
    with pytest.raises(InvalidSpecError, match="at least one tile"):
        ts.Dashboard("x", data=orders).build()


def test_too_big_a_table_is_refused_with_advice() -> None:
    big = superstore_like(4000, seed=3)
    dash = ts.Dashboard("Big", data=big, filters=["Order_ID"]).add("bar", x="Region", y="Sales")
    with ts.config(max_size_mb=0.1), pytest.raises(InvalidSpecError, match="Order_ID"):
        dash.build()


def test_hostile_values_stay_text_in_the_page() -> None:
    df = pd.DataFrame({"Name": EVIL, "Sales": [float(i + 1) for i in range(len(EVIL))]})
    dash = ts.Dashboard(EVIL[1], data=df, subtitle=EVIL[0], filters=["Name"]).add(
        "bar", x="Name", y="Sales"
    )
    page = dash.insights(3).to_html()
    tags, handlers = _parse(page)
    assert tags <= {"html", "head", "meta", "title", "style", "body", "main", "header", "h1", "p", "div", "script",
                    "section", "h2", "ul", "li"}, tags  # fmt: skip
    assert not handlers
    data = re.search(
        r'<script type="application/json" id="ts-dashboard">(.*?)</script>', page, re.S
    )
    assert data is not None and "<" not in data.group(1)
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page)
    assert csp is not None and len(scripts) >= 4
    import base64
    import hashlib

    for s in scripts:
        digest = base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
        assert f"sha256-{digest}" in csp.group(1).replace("&#x27;", "'")


def test_dashboards_never_change_the_input(orders: pd.DataFrame) -> None:
    before = orders.copy(deep=True)
    _dash(orders).insights().to_html()
    assert_unchanged(before, orders)


def test_notebook_display_is_sandboxed(orders: pd.DataFrame) -> None:
    html = ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales")._repr_html_()
    assert html.startswith('<iframe sandbox="allow-scripts" srcdoc="')


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_filters_from_the_address_bar_are_checked(orders: pd.DataFrame, tmp_path: Path) -> None:
    payload = _dash(orders).build()
    raw = [
        {
            "Region": {
                "type": "in",
                "values": ["West", "<img src=x onerror=alert(1)>"],
                "source": "evil",
            }
        },
        {"__w2": {"type": "in", "values": ["cur"]}, "Nope": {"type": "in", "values": ["x"]}},
        {"Order_Date|month": {"type": "range", "lo": "2015-01-01", "hi": "</script>"}},
        {
            "Order_Date|month": {"type": "range", "lo": "2015-01-01", "hi": "2015-06-01"},
            "Segment": {"type": "in", "values": [None]},
        },
        ["not", "an", "object"],
        {"Region": {"type": "in", "values": "West"}},
        {"Region": {"type": "in", "values": ["South"], "source": "t3", "mode": "highlight"}},
    ]
    got = _node(payload, [], tmp_path, sanitize=raw)["sanitized"]
    assert got[0] == {
        "Region": {"type": "in", "values": ["West"], "source": None, "mode": "filter"}
    }
    assert got[1] == {} and got[2] == {} and got[4] == {} and got[5] == {}
    assert got[3]["Order_Date|month"]["hi"] == "2015-06-01" and got[3]["Segment"]["values"] == [
        None
    ]
    assert got[6]["Region"] == {
        "type": "in",
        "values": ["South"],
        "source": "t3",
        "mode": "highlight",
    }


# ---------------------------------------------------------------- every other kind


MORE_TILES: list[dict[str, Any]] = [
    {"kind": "lollipop", "x": "Region", "y": "Sales"},
    {"kind": "combo", "x": "Category", "y": ["Sales", "Quantity"]},
    {"kind": "bullet", "x": "Region", "y": "Sales", "goal": 20000},
    {"kind": "bullet", "y": "Sales", "goal": 100000},
    {"kind": "gauge", "y": "Profit", "goal": 10000},
    {"kind": "funnel", "x": "Segment", "y": "Sales"},
    {"kind": "pareto", "x": "Sub_Category", "y": "Sales", "top": 5},
    {"kind": "waterfall", "x": "Region", "y": "Profit"},
    {"kind": "heatmap", "x": "Region", "color": "Category", "y": "Sales"},
    {"kind": "treemap", "x": ["Category", "Sub_Category"], "y": "Sales"},
    {"kind": "sunburst", "x": ["Region", "Segment"], "y": "Quantity"},
    {"kind": "sankey", "source": "Region", "target": "Category", "y": "Sales"},
    {"kind": "calendar_heatmap", "x": "Order_Date", "y": "Sales"},
    {"kind": "histogram", "x": "Sales", "bin_width": 100},
    {"kind": "scatter", "x": "Category", "y": ["Sales", "Profit"]},
    {"kind": "bubble", "x": "Region", "y": ["Sales", "Profit", "Quantity"], "color": "Segment"},
    {"kind": "symbol_map", "geo": "State", "y": "Sales"},
    {"kind": "density_map", "geo": "State", "y": "Sales"},
    {"kind": "flow_map", "source": "State", "target": "Hub", "y": "Sales"},
    {"kind": "bar", "x": "Region", "y": "Order_ID", "agg": "countd"},
    {"kind": "bar", "x": "Category", "y": "Sales", "agg": "median"},
    {"kind": "kpi", "y": "Order_ID", "agg": "countd"},
    {"kind": "table", "x": ["Region"], "y": ["Sales", "Discount"], "agg": "median"},
    {"kind": "boxplot", "x": "Category", "y": "Sales"},
    {"kind": "boxplot", "y": "Profit"},
    {"kind": "line", "x": "Discount", "y": "Sales"},
    {"kind": "multi_line", "x": "Quantity", "y": "Profit", "color": "Segment"},
]
MORE_FILTERS: list[dict[str, Any]] = [
    {},
    {"Region": {"type": "in", "values": ["West", "East"]}},
    {
        "Category": {"type": "in", "values": ["Technology"]},
        "Segment": {"type": "in", "values": ["Consumer"]},
    },
    {"Order_Date|month": {"type": "range", "lo": "2016-01-01", "hi": "2016-12-01"}},
]


def _close_deep(a: Any, b: Any, where: str) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        assert set(a) == set(b), (where, sorted(set(a) ^ set(b)))
        for k in a:
            _close_deep(a[k], b[k], f"{where}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), (where, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _close_deep(x, y, f"{where}[{i}]")
    elif isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        assert np.isclose(float(a), float(b), rtol=1e-9, atol=1e-9), (where, a, b)
    else:
        assert a == b, (where, a, b)


def _extract(option: dict[str, Any]) -> dict[str, Any]:
    opt = json.loads(json.dumps(option))
    axes = []
    for key in ("xAxis", "yAxis"):
        items = opt.get(key)
        for a in items if isinstance(items, list) else [items] if items else []:
            if a.get("type") == "category":
                axes.append(a["data"])
    series = [{"type": s.get("type"), "name": s.get("name"),
               "data": sorted(s["data"]) if s.get("name") == "Outliers" else s.get("data"),
               "links": s.get("links"), "max": s.get("max")} for s in opt.get("series", [])]  # fmt: skip

    vm = [opt["visualMap"]["min"], opt["visualMap"]["max"]] if opt.get("visualMap") else None
    cal = opt.get("calendar")
    cal = [c["range"] for c in (cal if isinstance(cal, list) else [cal])] if cal else None
    return {"axes": axes, "series": series, "vm": vm, "cal": cal}


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_every_other_kind_matches_python_after_filters(
    orders: pd.DataFrame, tmp_path: Path
) -> None:
    data = orders.assign(Hub=np.roll(orders["State"].to_numpy(), 7))
    dash = ts.Dashboard("More", data=data, filters=["Region", "Order_Date", "Category", "Segment"])
    for tile in MORE_TILES:
        dash.add(**tile)
    payload = dash.build()
    static = [(t["figure"]["kind"], t["static"]) for t in payload["tiles"] if "static" in t]
    assert not static, static
    deep = [t["id"] for t in payload["tiles"] if t["figure"]["kind"] not in ("kpi", "table", "bar")]
    results = _node(payload, MORE_FILTERS, tmp_path, deep=deep)
    for filters, tiles in zip(MORE_FILTERS, results, strict=True):
        for got in tiles:
            i = int(got["id"][1:])
            tile = dict(MORE_TILES[i])
            frame = _apply(data, filters)
            if tile["kind"] == "waterfall":  # steps keep the order of all the data while filtering
                tile["sort"] = list(dict.fromkeys(data[tile["x"]].dropna().astype(str)))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig = ts.chart(frame, tile.pop("kind"), colors=payload["colors"], **tile)
            where = f"tile {i} {MORE_TILES[i]} with {filters}"
            if "deep" in got:
                _close_deep(got["deep"], _extract(fig.option or {}), where)
            elif "kpi" in got:
                assert got["kpi"]["value_text"] == fig.kpi["value_text"], where  # type: ignore[index]
            elif "rows" in got:
                assert got["rows"] == fig.table["rows"], where  # type: ignore[index]
            else:
                want = _summary(fig, MORE_TILES[i])
                assert got["labels"] == want["labels"], where
                for name, values in want["series"].items():
                    assert all(
                        _close(a, b) for a, b in zip(got["series"][name], values, strict=True)
                    ), (where, name)
