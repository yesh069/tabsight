"""Choropleth and symbol maps (Phase 5): exact numbers, honest reporting, safe pages."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import tabsight as ts
from tabsight.charts.maps import project
from tabsight.warnings import DataWarning, InvalidSpecError

from .conftest import assert_unchanged

ROOT = Path(__file__).resolve().parent.parent


def counties() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "County": ["Cork", "Co. Cork", "Kerry", "Dublin", "Galway", "Atlantis"],
            "Revenue": [100.0, 50.0, 30.0, 400.0, 70.0, 5.0],
            "Margin": [0.10, 0.30, 0.20, 0.05, 0.15, 0.0],
        }
    )


def data_by_name(fig: ts.Figure) -> dict[str, Any]:
    assert fig.option is not None
    return {d["name"]: d["value"] for d in fig.option["series"][0]["data"]}


def test_choropleth_aggregates_exactly_and_reports_unmatched() -> None:
    df = counties()
    before = df.copy(deep=True)
    with pytest.warns(DataWarning, match="Atlantis"):
        fig = ts.chart(df, "map", geo="County", y="Revenue")
    assert_unchanged(before, df)
    assert fig.kind == "choropleth"
    values = data_by_name(fig)
    assert values == {
        "Cork": 150.0,
        "Kerry": 30.0,
        "Dublin": 400.0,
        "Galway": 70.0,
    }  # Cork + Co. Cork
    assert any("'Atlantis'" in n and "left out" in n for n in fig.notes)
    # an average is re-aggregated from its parts, never averaged twice
    avg = ts.chart(df, "map", geo="County", y="Margin", agg="mean", geo_map={"Atlantis": "Kerry"})
    assert data_by_name(avg)["Cork"] == pytest.approx(0.2)
    assert data_by_name(avg)["Kerry"] == pytest.approx(0.1)


def test_only_the_needed_shapes_go_into_the_page() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(counties(), "map", geo="County", y="Revenue")
    assert len(fig.maps) == 1
    entry = fig.maps[0]
    assert entry["name"] == "ts-IRL-iso" and list(entry["topo"]["objects"]) == ["iso"]
    assert set(entry["names"].values()) >= {"Cork", "Kerry", "Dublin"}
    page = fig.to_html()
    assert len(page) < 1_500_000
    assert fig.to_dict()["maps"][0]["object"] == "iso"


def test_world_map_projection_zoom_and_tiny_countries() -> None:
    df = pd.DataFrame(
        {"Country": ["France", "Germany", "Spain", "Italy", "Malta"], "Orders": [3, 4, 2, 2, 1]}
    )
    fig = ts.chart(df, "choropleth", geo="Country", y="Orders")
    geo = fig.option["geo"]  # type: ignore[index]
    assert geo["projection"] == {"$projection": "equal_earth"}
    assert geo["zoom"] > 1.6  # Europe only: zoomed in
    assert geo["center"] == pytest.approx(list(project("equal_earth", *_centre(df))), abs=1)
    dots = fig.option["series"][1]  # type: ignore[index]
    assert dots["type"] == "scatter" and [d["name"] for d in dots["data"]] == ["Malta"]
    assert "Equal Earth" in fig.explain() and "tiny countries" in fig.explain()
    merc = ts.chart(df, "map", geo="Country", y="Orders", projection="mercator")
    assert merc.option["geo"]["projection"] == {"$projection": "mercator"}  # type: ignore[index]


def _centre(df: pd.DataFrame) -> tuple[float, float]:
    from tabsight.geo import names as gn

    codes = {"France": "FRA", "Germany": "DEU", "Spain": "ESP", "Italy": "ITA", "Malta": "MLT"}
    pts = [gn.geo_data()["countries"][codes[c]]["label"] for c in df["Country"]]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    return (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2


def test_diverging_colours_for_negative_values() -> None:
    df = pd.DataFrame({"Nation": ["England", "Scotland", "Wales"], "Profit": [900.0, -120.0, 80.0]})
    fig = ts.chart(df, "map", geo="Nation", y="Profit")
    vm = fig.option["visualMap"]  # type: ignore[index]
    assert vm["min"] == -900 and vm["max"] == 900
    assert "diverge from zero" in fig.explain()
    assert fig.maps[0]["name"] == "ts-GBR-nation"


def test_us_map_with_insets_and_city_symbols(store: pd.DataFrame) -> None:
    states = ts.chart(store, "map", geo="State", y="Sales")
    assert states.maps[0]["name"] == "ts-USA-admin1"
    assert "Alaska and Hawaii" in states.explain()
    cities = pd.DataFrame(
        {"City": ["Anchorage", "Honolulu", "Austin", "Boston"], "Sales": [5.0, 3.0, 9.0, 1.0]}
    )
    fig = ts.chart(cities, "symbol_map", geo="City", y="Sales")
    pts = {d["name"].split(",")[0]: d for d in fig.option["series"][0]["data"]}  # type: ignore[index]
    assert pts["Anchorage"]["value"][1] < 32  # moved with the Alaska inset, below the lower 48
    assert pts["Austin"]["symbolSize"] > pts["Boston"]["symbolSize"]  # area grows with value
    assert fig.maps[0]["name"] == "ts-USA-admin1"


def test_coordinates_and_place_names_in_other_languages() -> None:
    pts = pd.DataFrame(
        {"lat": [53.35, 51.9, 999.0], "lon": [-6.26, -8.47, 0.0], "Sales": [5.0, 2.0, 1.0]}
    )
    fig = ts.chart(pts, "symbol_map", lat="lat", lon="lon", y="Sales")
    assert len(fig.option["series"][0]["data"]) == 2  # type: ignore[index]
    assert any("without valid coordinates" in n for n in fig.notes)
    df = pd.DataFrame({"Country": ["Germany", "India"], "Sales": [1.0, 2.0]})
    hindi = ts.chart(df, "map", geo="Country", y="Sales", geo_names="hi")
    assert set(data_by_name(hindi)) == {"जर्मनी", "भारत"}


def test_auto_draws_a_map_for_places(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "auto", x="State", y="Sales")
    assert fig.kind == "choropleth" and fig.lint().ok
    assert (
        ts.recommend(store, x="Region", y="Sales").best.kind == "bar"
    )  # sales regions aren't a map


def test_clear_errors(store: pd.DataFrame) -> None:
    df = counties()
    for kwargs, message in [
        ({"geo": "Product"}, "not found"),
        ({}, "needs geo="),
        ({"lat": "lat"}, "both lat= and lon="),
        ({"geo": "County", "map": "Ireland", "layer": "nation"}, "no 'nation' layer"),
        ({"geo": "County", "map": "Atlantis"}, "unknown country"),
        ({"geo": "County", "map": "world", "level": "region"}, "map='world'"),
        ({"geo": "County", "layer": "iso"}, "layer= needs map="),
    ]:
        with pytest.raises(InvalidSpecError, match=message), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ts.chart(df, "map", y="Revenue", **kwargs)
    with pytest.raises(InvalidSpecError, match="doesn't look like"):
        ts.chart(store, "map", geo="Segment", y="Sales")
    cities = pd.DataFrame({"City": ["Paris", "Tokyo", "Lagos"], "Sales": [1.0, 2.0, 3.0]})
    with pytest.raises(InvalidSpecError, match="symbol_map"):
        ts.chart(cities, "choropleth", geo="City", y="Sales")
    with pytest.raises(InvalidSpecError, match="geo_map"):
        ts.chart(df, "map", geo="County", y="Revenue", geo_map={"a": 1})  # type: ignore[dict-item]


# ---------------------------------------------------------------- security


def test_hostile_place_names_stay_text() -> None:
    evil = '<img src=x onerror=alert(1)>"</script>'
    df = pd.DataFrame({"County": ["Cork", evil, "Kerry"], "Revenue": [1.0, 2.0, 3.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(df, "map", geo="County", y="Revenue", title=evil, geo_map={evil: "Galway"})
    page = fig.to_html()
    figure_json = page.split('id="ts-figure">')[1].split("</script>")[0]
    assert "<img" not in figure_json and "</script" not in figure_json
    assert json.loads(figure_json)["title"] == evil  # escaped, not lost
    scripts = re.findall(r"<script(?:\s[^>]*)?>", page)
    assert len(scripts) == 5  # data, ECharts, topojson-client, runtime, init: nothing else


def test_map_page_csp_pins_topojson_client() -> None:
    import base64
    import hashlib

    from tabsight.render.assets import read_static

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        page = ts.chart(counties(), "map", geo="County", y="Revenue").to_html()
    digest = base64.b64encode(
        hashlib.sha256(read_static("topojson-client.min.js").encode()).digest()
    ).decode()
    assert f"sha256-{digest}" in page.split("Content-Security-Policy")[1].split(">")[0]
    assert "http://" not in page.split("<script")[0] and "connect-src" not in page
    plain = ts.chart(counties(), "bar", x="County", y="Revenue").to_html()
    assert digest not in plain  # only map pages carry the extra script


def test_country_file_names_are_checked() -> None:
    from tabsight.charts.maps import _country_topo

    for bad in ["../x", "irl", "IR", "IRL/../../etc"]:
        with pytest.raises(InvalidSpecError):
            _country_topo(bad)


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_python_and_javascript_projections_agree(tmp_path: Path) -> None:
    points = [
        [lon, lat]
        for lon in (-179.9, -120, -45, 0, 30, 90, 179.9)
        for lat in (-80, -55, -20, 0, 35, 60, 84)
    ]
    path = tmp_path / "points.json"
    path.write_text(json.dumps(points), encoding="utf-8")
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "projection.cjs"),
         str(ROOT / "src" / "tabsight" / "render" / "static" / "tabsight.js"), str(path)],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    js = json.loads(result.stdout)
    for name, projected in js.items():
        for (lon, lat), xy in zip(points, projected, strict=True):
            assert project(name, lon, lat) == pytest.approx(tuple(xy), abs=1e-9), (name, lon, lat)
