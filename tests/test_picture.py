"""Still SVG pictures (fig.to_svg) and the picture a saved notebook shows when it can't run scripts."""

from __future__ import annotations

import re
import threading
import warnings
from pathlib import Path

import pandas as pd
import pytest

import tabsight as ts
from tabsight.render import picture
from tabsight.spec import CHART_KINDS
from tabsight.warnings import InvalidSpecError

from .test_html_security import EVIL
from .test_phase6_charts import KIND_ARGS, _evil

pytest.importorskip("dukpy", exc_type=ImportError)  # also skips where the system blocks its DLL


@pytest.fixture(autouse=True)
def _no_size_tip(monkeypatch: pytest.MonkeyPatch) -> None:
    import tabsight.figure as figure

    monkeypatch.setattr(
        figure, "_NOTEBOOK", {"bytes": 0, "tipped": 1}
    )  # the 10 MB tip is tested elsewhere


SVG_TAGS = {"svg", "g", "path", "rect", "text", "line", "circle", "polyline", "polygon", "ellipse",
            "defs", "clipPath", "linearGradient", "radialGradient", "stop", "tspan", "image", "pattern",
            "style", "title", "desc", "use", "mask", "filter"}  # fmt: skip


def _parse(svg: str) -> list[tuple[str, dict[str, str]]]:
    from defusedxml.ElementTree import fromstring

    root = fromstring(svg)  # well-formed XML, or this raises
    return [(el.tag.split("}")[-1], dict(el.attrib)) for el in root.iter()]


def _is_safe(svg: str) -> None:
    for tag, attrs in _parse(svg):
        assert tag in SVG_TAGS, f"unexpected tag {tag}"
        assert tag != "script" and tag != "foreignObject"
        for name, value in attrs.items():
            assert not name.lower().startswith("on"), f"event handler {name} on {tag}"
            assert "javascript:" not in value.lower()
            if name.endswith("href"):
                assert value.startswith(("#", "data:image/")), f"{tag} links to {value[:40]}"


@pytest.mark.parametrize("kind", sorted(CHART_KINDS))
def test_every_kind_draws_a_safe_picture_of_hostile_data(kind: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = ts.chart(_evil(), kind, title=EVIL[1], subtitle=EVIL[0], **KIND_ARGS[kind])
    if kind in picture.NO_PICTURE:
        with pytest.raises(InvalidSpecError, match="canvas"):
            fig.to_svg()
        assert fig._repr_html_().startswith("<iframe")  # the notebook still shows the live chart
        return
    svg = fig.to_svg()
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    _is_safe(svg)
    assert "&lt;/script&gt;&lt;script&gt;alert(2)" in svg  # the title is shown as text


def test_picture_has_title_notes_and_the_theme(store: pd.DataFrame) -> None:
    import dataclasses

    fig = ts.chart(store, "bar", x="Sub_Category", y="Sales", theme="dark", subtitle="Q4")
    fig = dataclasses.replace(fig, notes=("a note under the chart " * 12,))
    svg = fig.to_svg(width=640)
    assert 'width="640"' in svg and "Sum of Sales by Sub Category" in svg and ">Q4<" in svg
    assert fig.theme.tile in svg
    lines = re.findall(r">([^<]*note[^<]*)</text>", svg)
    assert svg.count("note") == 12 and len(lines) >= 2  # wrapped over lines
    kpi = ts.chart(store, "kpi", y="Sales").to_svg()
    assert re.search(r">\$\d", kpi)
    table = ts.chart(store, "table", x="Order_ID", y="Sales").to_svg()
    assert "more rows in the interactive table" in table


def test_to_svg_writes_a_file(store: pd.DataFrame, tmp_path: Path) -> None:
    out = tmp_path / "chart.svg"
    svg = ts.chart(store, "bar", x="Region", y="Sales").to_svg(out)
    assert out.read_text(encoding="utf-8") == svg


@pytest.mark.parametrize("width", [0, 199, 4001, 800.0, "800", True])
def test_to_svg_width_is_checked(store: pd.DataFrame, width: object) -> None:
    with pytest.raises(InvalidSpecError, match="width"):
        ts.chart(store, "bar", x="Region", y="Sales").to_svg(width=width)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [
        "<svg><script>alert(1)</script></svg>",
        '<svg><rect onload="alert(1)"/></svg>',
        "<svg><foreignObject><div/></foreignObject></svg>",
        '<svg><a xlink:href="https://example.com"><text>x</text></a></svg>',
        '<svg><image href="https://example.com/x.png"/></svg>',
    ],
)
def test_unsafe_pictures_are_refused(bad: str) -> None:
    with pytest.raises(InvalidSpecError, match="not allowed"):
        picture._check(bad)


def test_text_that_looks_like_markup_is_allowed() -> None:
    assert picture._check("<svg><text>a&quot; onload=&quot;x javascript:</text></svg>")


def test_pictures_can_be_drawn_from_several_threads(store: pd.DataFrame) -> None:
    figs = [
        ts.chart(store, "bar", x="Region", y="Sales"),
        ts.chart(store, "map", geo="State", y="Sales"),
    ]
    out: list[str] = []

    def draw(fig: ts.Figure) -> None:
        out.append(fig.to_svg())

    threads = [threading.Thread(target=draw, args=(figs[i % 2],)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(out) == 6 and len(set(out)) == 2  # the same chart always gives the same picture


# ---------------------------------------------------------------- notebooks


def test_notebook_output_stacks_the_live_chart_on_the_picture(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    html = fig._repr_html_()
    assert html.startswith('<div style="display:grid">')
    img, frame = html.split("<iframe", 1)
    assert 'src="data:image/svg+xml;base64,' in img and 'alt="Sum of Sales by Region"' in img
    assert img.index("<img") < html.index("<iframe")  # the live chart is drawn on top
    assert 'sandbox="allow-scripts"' in frame


def test_notebook_picture_can_be_turned_off(store: pd.DataFrame) -> None:
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    with ts.config(picture=False):
        assert fig._repr_html_().startswith("<iframe")
    with pytest.raises(InvalidSpecError):
        ts.set_defaults(picture="yes")


def test_notebook_works_without_dukpy(store: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(picture, "available", lambda: False)
    assert ts.chart(store, "bar", x="Region", y="Sales")._repr_html_().startswith("<iframe")


def test_a_failed_or_huge_picture_never_breaks_the_notebook(
    store: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tabsight.figure as figure

    fig = ts.chart(store, "bar", x="Region", y="Sales")

    def broken(*_: object, **__: object) -> str:
        raise RuntimeError("engine failed")

    monkeypatch.setattr(picture, "figure_svg", broken)
    assert fig._repr_html_().startswith("<iframe")
    monkeypatch.undo()
    monkeypatch.setattr(figure, "PICTURE_MAX_BYTES", 10)
    assert fig._repr_html_().startswith("<iframe")


def test_missing_dukpy_gives_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, store: pd.DataFrame
) -> None:
    import builtins

    real = builtins.__import__

    failure: list[ImportError] = [ModuleNotFoundError("dukpy")]

    def no_dukpy(name: str, *args: object, **kwargs: object) -> object:
        if name == "dukpy":
            raise failure[0]
        return real(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(picture, "_engine", {})
    monkeypatch.setattr(builtins, "__import__", no_dukpy)
    fig = ts.chart(store, "bar", x="Region", y="Sales")
    with pytest.raises(InvalidSpecError, match=r"tabsight\[static\]"):
        fig.to_svg()
    failure[0] = ImportError(
        "DLL load failed: blocked by policy"
    )  # installed, but the system refuses it
    with pytest.raises(InvalidSpecError, match="could not be loaded: DLL load failed"):
        fig.to_svg()
    assert not picture.available() and fig._repr_html_().startswith("<iframe")
