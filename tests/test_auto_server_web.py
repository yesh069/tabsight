"""ts.auto, the command line, server mode, web helpers and PNG export."""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import threading
import types
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

import tabsight as ts
from tabsight.cli import main
from tabsight.localserver import make_server
from tabsight.server import MAX_REQUEST_BYTES, BadRequest
from tabsight.warnings import InvalidSpecError

from .conftest import assert_unchanged, superstore_like
from .test_dashboard import (
    FILTERS,
    MORE_FILTERS,
    MORE_TILES,
    TILES,
    _apply,
    _close_deep,
    _flat,
    _node,
)

# ---------------------------------------------------------------- ts.auto

ODD_DATA = {
    "superstore": superstore_like(800, seed=3),
    "text only": pd.DataFrame({"name": ["a", "b", "c"] * 5, "note": ["x"] * 15}),
    "numbers only": pd.DataFrame({"a": np.arange(20.0), "b": np.arange(20.0) ** 2}),
    "countries": pd.DataFrame(
        {
            "Country": ["France", "Germany", "Spain", "Italy", "Ireland"] * 4,
            "Sales": np.arange(20.0),
        }
    ),
    "daily": pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=100),
            "Value": np.random.default_rng(1).normal(size=100),
        }
    ),
    "one row": pd.DataFrame({"x": ["a"], "y": [1.0]}),
    "missing values": pd.DataFrame(
        {"Team": ["A", None, "B", "C"] * 10, "Score": [1.0, np.nan, 3.0, 4.0] * 10}
    ),
}


@pytest.mark.parametrize("name", list(ODD_DATA))
def test_auto_makes_a_dashboard_from_any_table(name: str) -> None:
    df = ODD_DATA[name]
    before = df.copy()
    dash = ts.auto(df, name)
    assert dash.tiles and dash.decisions
    page = dash.to_html()
    assert "<!doctype html>" in page
    assert_unchanged(before, df)


def test_auto_choices_on_sales_data() -> None:
    dash = ts.auto(ODD_DATA["superstore"])
    kinds = [t["kind"] for t in dash.tiles]
    assert kinds[:4] == ["kpi"] * 4 and dash.tiles[0]["y"] == "Sales"  # money first
    assert dash.tiles[0]["compare"] == "previous_year"  # four years of dates
    line = next(t for t in dash.tiles if t["kind"] == "line")
    assert line["x"] == "Order_Date" and line["freq"] == "month"
    assert any(t["kind"] == "map" and t["geo"] == "State" for t in dash.tiles)
    assert dash.filters[0] == "Order_Date" and dash.insight_count
    assert any(d.startswith("map: State") for d in dash.decisions)
    # same data, same dashboard
    assert ts.auto(ODD_DATA["superstore"]).to_dict() == dash.to_dict()


def test_auto_counts_rows_when_there_is_no_measure() -> None:
    dash = ts.auto(ODD_DATA["text only"])
    assert dash.tiles[0] == {"kind": "kpi", "w": 12, "action": "filter", "y": "Records"}
    assert "Records" not in ODD_DATA["text only"].columns  # added to tabsight's copy only


def test_auto_rejects_bad_arguments() -> None:
    with pytest.raises(InvalidSpecError, match="max_tiles"):
        ts.auto(ODD_DATA["superstore"], max_tiles=0)
    with pytest.raises(InvalidSpecError):
        ts.auto(pd.DataFrame())


def test_auto_respects_max_tiles_and_the_size_limit() -> None:
    assert len(ts.auto(ODD_DATA["superstore"], max_tiles=3).tiles) == 3
    big = superstore_like(3000, seed=3)  # its table is about 0.13 MB
    with ts.config(max_size_mb=0.1):
        dash = ts.auto(big)
    assert any("size limit" in d for d in dash.decisions)
    with ts.config(max_size_mb=0.1):
        dash.build()  # fits now


# ---------------------------------------------------------------- command line


@pytest.fixture
def csv(tmp_path: Path) -> Path:
    path = tmp_path / "sales_2024.csv"
    superstore_like(500, seed=5).to_csv(path, index=False)
    return path


def test_cli_auto_build_and_data_tools(
    csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, spec = tmp_path / "dash.html", tmp_path / "spec.json"
    assert main(["auto", str(csv), "-o", str(out), "--save", str(spec), "--theme", "dark"]) == 0
    assert "Sales 2024" in out.read_text(encoding="utf-8")  # title from the file name
    printed = capsys.readouterr().out
    assert "measures:" in printed and "wrote" in printed
    assert main(["build", str(spec), str(csv), "-o", str(tmp_path / "again.html"), "-q"]) == 0
    assert (tmp_path / "again.html").stat().st_size > 100_000
    assert (
        main(
            [
                "chart",
                str(csv),
                "bar",
                "--x",
                "Region",
                "--y",
                "Sales",
                "-o",
                str(tmp_path / "bar.html"),
            ]
        )
        == 0
    )
    assert main(["profile", str(csv)]) == 0
    assert "Sales" in capsys.readouterr().out
    assert main(["recommend", str(csv), "--x", "Region", "--y", "Sales"]) == 0
    assert "bar" in capsys.readouterr().out
    assert main(["check", str(csv)]) == 0
    assert main(["clean", str(csv), "-q"]) == 0
    assert (tmp_path / "sales_2024.clean.csv").exists()


def test_cli_refuses_to_overwrite_its_input_and_reports_errors(
    csv: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = csv.read_bytes()
    assert main(["auto", str(csv), "-o", str(csv)]) == 2
    assert csv.read_bytes() == before
    assert main(["auto", str(csv.with_name("missing.csv"))]) == 2
    err = capsys.readouterr().err
    assert "overwrite the input" in err and "no such file" in err
    assert main(["build", str(csv), str(csv), "--data", "nonsense"]) == 2
    assert main([]) == 0  # help


def test_cli_runs_as_a_module(csv: Path, tmp_path: Path) -> None:
    import subprocess

    out = tmp_path / "m.html"
    run = subprocess.run([sys.executable, "-m", "tabsight", "auto", str(csv), "-o", str(out), "-q"],
                         capture_output=True, text=True, timeout=300)  # fmt: skip
    assert run.returncode == 0, run.stderr
    assert out.exists()


# ---------------------------------------------------------------- server mode


@pytest.fixture(scope="module")
def orders() -> pd.DataFrame:
    df = superstore_like(900, seed=11)
    df.loc[::37, "Segment"] = None
    return df


def _all_tiles(server: ts.DashboardServer) -> list[dict[str, Any]]:
    return [
        {"id": t["id"], "view": 0, "drill": [], "theme": "light"} for t in server.payload()["tiles"]
    ]


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
@pytest.mark.parametrize("which", ["core", "more"])
def test_server_mode_gives_the_same_numbers_as_the_offline_page(orders: pd.DataFrame, tmp_path: Path,
                                                                which: str) -> None:  # fmt: skip
    data = orders.assign(Hub=np.roll(orders["State"].to_numpy(), 7))
    tiles, filters = (TILES, FILTERS) if which == "core" else (MORE_TILES, MORE_FILTERS)
    dash = ts.Dashboard(
        "Server", data=data, filters=["Region", "Order_Date", "Segment", "Category"]
    )
    for tile in tiles:
        dash.add(**tile)
    built = dash.build()
    deep = [t["id"] for t in _flat(built) if t["figure"]["kind"] not in ("kpi", "table", "bar")]
    offline = _node(built, filters, tmp_path, deep=deep)
    server = dash.server("/data")
    payload = server.payload()
    assert payload["data"]["rows"] == 0 and payload["server"] == {
        "url": "/data"
    }  # no rows in the page
    tables = []
    for f in filters:
        reply = server.respond(json.dumps({"state": f, "tiles": _all_tiles(server)}))
        tables.append({tid: answer["table"] for tid, answer in reply["tiles"].items()})
        for answer in reply["tiles"].values():  # each table is smaller than the whole
            assert answer["table"]["rows"] <= max(1, len(data))
    data_file = tmp_path / "cases.json"
    cases = {"payload": payload, "filters": filters, "tables": tables, "deep": deep}
    data_file.write_text(json.dumps(cases), encoding="utf-8")
    import subprocess

    from .test_dashboard import SCRIPT, STATIC

    run = subprocess.run(["node", str(SCRIPT), str(STATIC / "tabsight.js"), str(STATIC / "dashboard.js"),
                          str(data_file)], capture_output=True, text=True, encoding="utf-8", check=True, timeout=120)  # fmt: skip
    _close_deep(json.loads(run.stdout), offline, which)  # sums may differ in the last digit only


def test_server_mode_redraws_static_tiles_from_the_filtered_rows(orders: pd.DataFrame) -> None:
    dash = ts.Dashboard("Static", data=orders, filters=["Region", "State"]).add(
        "scatter", x="Sales", y="Profit"
    )
    server = dash.server("/data")
    state = {"Region": {"type": "in", "values": ["West"]}}
    reply = server.respond({"state": state, "tiles": _all_tiles(server)})
    figure = reply["tiles"]["t0"]["figure"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        want = ts.chart(_apply(orders, state), "scatter", x="Sales", y="Profit").to_dict()
    assert figure["option"]["series"] == want["option"]["series"]
    west, south = state["Region"], {"type": "in", "values": ["Florida"]}  # Florida is in the South
    empty = server.respond({"state": {"Region": west, "State": south}, "tiles": _all_tiles(server)})
    assert empty["tiles"]["t0"] == {"empty": True}


def test_server_mode_insights_and_drill_tables(orders: pd.DataFrame) -> None:
    dash = (ts.Dashboard("Drill", data=orders, filters=["Region"]).add("bar", x="Order_Date", y="Sales", freq="year")
            .insights())  # fmt: skip
    server = dash.server("/data")
    views = server.payload()["tiles"][0]["views"]
    drill = next(i for i, v in enumerate(views) if v.get("drill"))
    item = {"id": "t0", "view": drill, "drill": ["Order_Date|year"], "theme": "light"}
    reply = server.respond(
        {"state": {"Region": {"type": "in", "values": ["East"]}}, "tiles": [item], "insights": True}
    )
    assert (
        "Order_Date|year" in reply["tiles"]["t0"]["table"]["dims"]
    )  # the page applies the drill step
    assert "Region" not in reply["tiles"]["t0"]["table"]["dims"]  # the server applied the filter
    assert reply["insights"]["rows"] > 0


BAD_REQUESTS: list[Any] = [
    b"not json",
    b"[1, 2]",
    "too big",
    {"tiles": "t0"},
    {"tiles": [{"id": "t99"}]},
    {"tiles": [{"id": "t0", "view": 99}]},
    {"tiles": [{"id": "t0", "view": True}]},
    {"tiles": [{"id": "t0", "drill": ["Profit; DROP TABLE"]}]},
    {"tiles": [{"id": "t0"}] * 50},
    "deeply nested",
]


@pytest.mark.parametrize("body", BAD_REQUESTS, ids=range(len(BAD_REQUESTS)))
def test_malformed_requests_are_refused(orders: pd.DataFrame, body: Any) -> None:
    server = ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales").server("/data")
    if body == "too big":
        body = b"x" * (MAX_REQUEST_BYTES + 1)
    if body == "deeply nested":  # RecursionError inside json.loads must still be a 400
        body = b"[" * 100_000 + b"]" * 100_000
    with pytest.raises(BadRequest):
        server.respond(body)


def test_unknown_filters_are_dropped_not_obeyed(orders: pd.DataFrame) -> None:
    server = (
        ts.Dashboard("x", data=orders, filters=["Region"])
        .add("bar", x="Region", y="Sales")
        .server("/data")
    )
    raw = {
        "Region": {"type": "in", "values": ["West", "<script>", 5], "source": "evil", "mode": "x"},
        "Sales": {"type": "in", "values": ["1"]},  # not a dimension
        "__dim0__": {"type": "in", "values": ["West"]},
        "Order_Date|month": {"type": "range", "lo": "0000", "hi": "9999"},
        "Nope": "x",
    }
    assert server.sanitize(raw) == {
        "Region": {"type": "in", "values": ["West"], "source": None, "mode": "filter"}
    }
    assert server.sanitize("junk") == {}


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "/a b", "/a'b", "//evil.example", "ftp://x", "", 5]
)
def test_server_address_is_checked(orders: pd.DataFrame, url: Any) -> None:
    with pytest.raises(InvalidSpecError, match="url"):
        ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales").server(url)


def test_server_page_may_only_talk_to_its_own_address(orders: pd.DataFrame) -> None:
    dash = ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales")
    assert "connect-src" not in dash.to_html()  # offline pages send nothing anywhere
    assert "connect-src &#x27;self&#x27;;" in dash.server("/sales/data").page()
    assert "connect-src https://api.example.com;" in dash.server("https://api.example.com/x").page()


# ---------------------------------------------------------------- web frameworks


def test_stdlib_server(orders: pd.DataFrame) -> None:
    dash = ts.Dashboard("Local", data=orders, filters=["Region"]).add("bar", x="Region", y="Sales")
    httpd = make_server(dash, port=0, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        with urllib.request.urlopen(base + "/") as r:
            assert r.headers["X-Content-Type-Options"] == "nosniff"
            assert b"connect-src" in r.read()
        body = json.dumps({"state": {"Region": {"type": "in", "values": ["West"]}},
                           "tiles": [{"id": "t0", "view": 0}]}).encode()  # fmt: skip
        req = urllib.request.Request(
            base + "/data", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())["tiles"]["t0"]["table"]["rows"] >= 1
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(
                urllib.request.Request(
                    base + "/data", data=b"nope", headers={"Content-Type": "application/json"}
                )
            )
        assert e.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/etc/passwd")
        assert e.value.code == 404
        # DNS rebinding: a page on another domain pointed at 127.0.0.1 still sends its own Host
        for method, path, payload in (("GET", "/", None), ("POST", "/data", body)):
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=10)
            headers = {
                "Host": f"attacker.example:{httpd.server_port}",
                "Content-Type": "application/json",
            }
            conn.request(method, path, body=payload, headers=headers)
            assert conn.getresponse().status == 421, method
            conn.close()
        # a cross-site form or fetch can only send text/plain without asking first
        plain = urllib.request.Request(
            base + "/data", data=body, headers={"Content-Type": "text/plain"}
        )
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(plain)
        assert e.value.code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def _client_checks(get: Any, post: Any) -> None:  # post(path, body, content_type=JSON)
    page = get("/sales")
    assert page.status_code == 200 and page.headers["x-content-type-options"] == "nosniff"
    good = post("/sales/data", json.dumps({"tiles": [{"id": "t0", "view": 0}]}))
    plain = post("/sales/data", json.dumps({"tiles": [{"id": "t0", "view": 0}]}), "text/plain")
    assert (
        plain.status_code == 415
    )  # a cross-site form or fetch can't send JSON without a preflight
    assert good.status_code == 200 and good.json()["tiles"]["t0"]["table"]["rows"] == 4
    bad = post("/sales/data", "nope")
    assert bad.status_code == 400 and bad.json() == {"error": "bad request"}  # nothing echoed
    assert post("/sales/data", "x" * (MAX_REQUEST_BYTES + 1)).status_code == 413


def test_fastapi_router(orders: pd.DataFrame) -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    app = fastapi.FastAPI()
    app.include_router(
        ts.web.fastapi_router(
            ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales"), "/sales"
        )
    )
    client = TestClient(app)
    _client_checks(
        client.get,
        lambda path, body, kind="application/json": client.post(
            path, content=body, headers={"Content-Type": kind}
        ),
    )


def test_flask_blueprint(orders: pd.DataFrame) -> None:
    flask = pytest.importorskip("flask")
    app = flask.Flask("t")
    app.register_blueprint(
        ts.web.flask_blueprint(
            ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales"), "/sales"
        )
    )
    client = app.test_client()

    class Reply:  # the same shape as the FastAPI client's replies
        def __init__(self, r: Any) -> None:
            self.status_code, self.headers, self._r = (
                r.status_code,
                {k.lower(): v for k, v in r.headers},
                r,
            )

        def json(self) -> Any:
            return self._r.get_json()

    _client_checks(
        lambda p: Reply(client.get(p)),
        lambda p, body, kind="application/json": Reply(
            client.post(p, data=body, content_type=kind)
        ),
    )


def test_web_paths_are_checked(orders: pd.DataFrame) -> None:
    dash = ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales")
    with pytest.raises(InvalidSpecError, match="path"):
        ts.web._server(dash, "sales")
    with pytest.raises(InvalidSpecError, match="answers"):
        ts.web._server(dash.server("/other/data"), "/sales")


def test_serve_payload_and_embeds(orders: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    fig = ts.chart(orders, "bar", x="Region", y="Sales")
    dash = ts.Dashboard("x", data=orders).add("bar", x="Region", y="Sales")
    assert ts.serve_payload(fig) == fig.to_dict()
    assert ts.serve_payload(dash)["tiles"][0]["id"] == "t0"
    assert ts.serve_payload(dash.server("/d"))["data"]["rows"] == 0
    assert "tiles" in ts.serve_payload(dash.server("/d"), {"tiles": []})
    assert ts.serve_payload(orders.head(200))["tiles"]
    with pytest.raises(InvalidSpecError):
        ts.serve_payload("SELECT 1")

    calls: dict[str, Any] = {}
    components = types.ModuleType("streamlit.components.v1")
    components.html = lambda html, **kw: calls.update(streamlit=(html, kw))  # type: ignore[attr-defined]
    for name in ("streamlit", "streamlit.components"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "streamlit.components.v1", components)
    ts.streamlit(fig)
    assert (
        calls["streamlit"][0].startswith("<!doctype html>")
        and calls["streamlit"][1]["height"] > 400
    )

    html_mod = types.ModuleType("dash.html")
    html_mod.Iframe = lambda **kw: kw  # type: ignore[attr-defined]
    dash_mod = types.ModuleType("dash")
    dash_mod.html = html_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dash", dash_mod)
    monkeypatch.setitem(sys.modules, "dash.html", html_mod)
    frame = ts.web.dash_iframe(dash, id="sales")
    assert frame["sandbox"] == "allow-scripts allow-downloads" and frame["id"] == "sales"
    with pytest.raises(InvalidSpecError):
        ts.web.dash_iframe("<b>")


# ---------------------------------------------------------------- PNG


def test_png_export(orders: pd.DataFrame, tmp_path: Path) -> None:
    pytest.importorskip("dukpy", exc_type=ImportError)  # Application Control may block its DLL
    pytest.importorskip("resvg_py", exc_type=ImportError)
    fig = ts.chart(orders, "bar", x="Region", y="Sales")
    png = fig.to_png(tmp_path / "bar.png", width=600, scale=1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and (tmp_path / "bar.png").read_bytes() == png
    width = int.from_bytes(fig.to_png(width=600, scale=2)[16:20], "big")
    assert width == 2 * int.from_bytes(png[16:20], "big")
    with pytest.raises(InvalidSpecError, match="scale"):
        fig.to_png(scale=100)


def test_auto_maps_regions_before_cities() -> None:
    sample = ts.load(Path(__file__).resolve().parent.parent / "examples" / "superstore_sample.csv")
    maps = [t for t in ts.auto(sample).tiles if t["kind"] in ("map", "symbol_map")]
    assert maps == [{"kind": "map", "w": 6, "action": "filter", "geo": "State", "y": "Sales"}]
    cities = pd.DataFrame(
        {"City": ["Paris", "Berlin", "Madrid", "Rome", "Dublin"] * 4, "Sales": np.arange(20.0)}
    )
    assert [t["kind"] for t in ts.auto(cities).tiles if "geo" in t] == [
        "symbol_map"
    ]  # points, not regions
