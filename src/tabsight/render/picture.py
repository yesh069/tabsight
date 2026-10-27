"""Static SVG pictures of figures, drawn in Python without a browser.

ECharts can draw a chart to an SVG string on its own ("server-side rendering"). tabsight
runs it inside dukpy, a small JavaScript engine for Python (``pip install tabsight[static]``).
The picture is used by ``Figure.to_svg()`` and as the fallback a notebook shows when it is
reopened untrusted or viewed on GitHub, where the interactive chart cannot run.

Security:

- Only tabsight's own bundled scripts are run. The figure goes in as a JSON string and is
  read with ``JSON.parse``; data is never pasted into JavaScript source.
- ECharts escapes text in the SVG it writes; every text tabsight adds goes through
  ``html.escape``. ``_check`` refuses any picture that still contains script, event
  handlers, foreign objects or links, in case a future ECharts changes behaviour.
- In a notebook the picture is a base64 ``data:`` image, and browsers never run scripts
  inside an SVG shown as an image.
"""

from __future__ import annotations

import base64
import html
import json
import re
import threading
from typing import Any

from tabsight.render.assets import read_static
from tabsight.warnings import InvalidSpecError

__all__ = ["available", "data_uri", "figure_svg"]

WIDTH = 800
NO_PICTURE = ("density_map",)  # ECharts draws the heat layer on a canvas only
_PAD = 12
_NOTE_CHARS = 110
_TABLE_ROWS = 25
_engine: dict[str, Any] = {}
_lock = threading.Lock()  # one dukpy interpreter, not safe to share between threads
_UNSAFE = re.compile(
    r"<\s*(script|foreignObject|iframe|object|embed|a\b)|\bon[a-z]+\s*=|javascript:|href", re.I
)

_DRAW = """
var fig = JSON.parse(dukpy.fig);
tabsight.registerMaps(fig.maps);
var option = tabsight.hydrate(fig.option, fig.locales || {});
var aspects = tabsight.fitAspects(option);
option.animation = false;
option.backgroundColor = fig.theme.tile;
var chart = echarts.init(null, null, {renderer: "svg", ssr: true, width: dukpy.width, height: fig.height});
chart.setOption(option);
tabsight.fitMaps(chart, aspects);
var svg = chart.renderToSVGString();
chart.dispose();
svg;
"""


def available() -> bool:
    """True when dukpy is installed, so charts can be drawn as pictures."""
    try:
        import dukpy  # noqa: F401
    except ImportError:
        return False
    return True


def _interpreter() -> Any:
    if "js" not in _engine:
        try:
            import dukpy
        except ModuleNotFoundError:
            raise InvalidSpecError(
                "drawing a chart as a picture needs dukpy: pip install tabsight[static]"
            ) from None
        except ImportError as err:  # installed, but the system refused to load it
            raise InvalidSpecError(f"dukpy is installed but could not be loaded: {err}") from None
        js = dukpy.JSInterpreter()
        # ECharts schedules redraws with timers; a server-side draw happens at once without them.
        js.evaljs(
            "var globalThis = this; var setTimeout = function () { return 0; };"
            "var clearTimeout = function () {};"
        )
        for name in ("echarts.min.js", "topojson-client.min.js", "tabsight.js"):
            js.evaljs(read_static(name))
        _engine["js"] = js
    return _engine["js"]


def _chart_svg(figure: dict[str, Any], width: int) -> str:
    if figure["kind"] in NO_PICTURE:
        raise InvalidSpecError(
            f"a {figure['kind'].replace('_', ' ')} is drawn on a canvas, so it has no still picture"
        )
    with _lock:
        js = _interpreter()
        svg = js.evaljs(_DRAW, fig=json.dumps(figure, allow_nan=False), width=width)
    if not isinstance(svg, str) or not svg.startswith("<svg"):
        raise InvalidSpecError("ECharts did not return an SVG picture")
    # ECharts numbers charts and styles across the session (zr6-cls-22); renumbering from
    # zero keeps the same chart giving the same picture
    svg = re.sub(r"\bzr\d+-", "ts-", svg)
    names: dict[str, str] = {}
    return re.sub(r"ts-cls-\d+", lambda m: names.setdefault(m.group(), f"ts-cls-{len(names)}"), svg)


def _check(svg: str) -> str:
    markup = re.sub(r">[^<]*<", "><", svg)  # text between tags is escaped, so only tags are checked
    if _UNSAFE.search(markup):
        raise InvalidSpecError("the picture contains markup that is not allowed in a static image")
    return svg


def _wrap(text: str, chars: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > chars:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    return lines + ([line] if line else [])


def _text(x: float, y: float, value: str, size: float, color: str, weight: int = 400,
          anchor: str = "start") -> str:  # fmt: skip
    return (
        f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" font-weight="{weight}" fill="{color}" '
        f'text-anchor="{anchor}">{html.escape(value)}</text>'
    )


def figure_svg(figure: dict[str, Any], *, width: int = WIDTH) -> str:
    """One SVG card for a figure (``Figure.to_dict()``): title, chart, notes."""
    if type(width) is not int or not 200 <= width <= 4000:
        raise InvalidSpecError("width must be a whole number of pixels from 200 to 4000")
    theme = figure["theme"]
    kind = figure["kind"]
    parts: list[str] = []
    y = 26.0
    parts.append(_text(16, y, figure.get("title") or "", 15, theme["text"], 650))
    if figure.get("subtitle"):
        y += 18
        parts.append(_text(16, y, figure["subtitle"], 12.5, theme["text_secondary"]))
    head = y + 14
    parts.append(f'<rect x="0" y="0" width="{width}" height="{head:g}" fill="{theme["header"]}"/>')
    parts.insert(0, parts.pop())  # the header band goes under the title
    parts.append(
        f'<line x1="0" x2="{width}" y1="{head:g}" y2="{head:g}" stroke="{theme["border"]}"/>'
    )
    y = head + 8
    if kind == "kpi":
        kpi = figure["kpi"]
        y += 46
        parts.append(_text(_PAD + 8, y, kpi["value_text"], 40, theme["text"], 700))
        for extra in (kpi.get("label"), kpi.get("detail")):
            if extra:
                y += 20
                parts.append(_text(_PAD + 8, y, extra, 13, theme["text_secondary"]))
        y += 12
    elif kind == "table":
        y = _table(figure["table"], theme, parts, y, width)
    else:
        inner = _chart_svg(figure, width - 2 * _PAD)
        parts.append(f'<g transform="translate({_PAD},{y:g})">{inner}</g>')
        y += int(figure["height"])
    notes = list(figure.get("notes") or [])
    if kind == "table" and figure["table"].get("note"):
        notes.append(figure["table"]["note"])
    for note in notes:
        for line in _wrap(note, int(_NOTE_CHARS * width / WIDTH)):
            y += 18
            parts.append(_text(16, y, line, 12, theme["text_secondary"]))
    found = figure.get("insights") or []
    if found:
        y += 26
        parts.append(_text(16, y, "INSIGHTS", 11, theme["text_secondary"], 650))
        for item in found:
            for k, line in enumerate(_wrap(item["text"], int(_NOTE_CHARS * width / WIDTH) - 4)):
                y += 19
                parts.append(_text(30, y, line, 13, theme["text"]))
                if k == 0:
                    parts.append(
                        f'<circle cx="21" cy="{y - 4:g}" r="2" fill="{theme["text_secondary"]}"/>'
                    )
    height = int(y + 14)
    body = "".join(parts)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{html.escape(theme["font"])}">'
        f'<rect width="{width}" height="{height}" rx="{int(theme["radius"])}" fill="{theme["tile"]}" '
        f'stroke="{theme["border"]}"/>{body}</svg>'
    )
    return _check(svg)


def _table(
    table: dict[str, Any], theme: dict[str, Any], parts: list[str], y: float, width: int
) -> float:
    columns = table["columns"]
    rows = table["rows"][:_TABLE_ROWS]
    span = (width - 2 * _PAD) / max(len(columns), 1)

    def row(cells: list[str], top: float, weight: int) -> None:
        for i, (cell, col) in enumerate(zip(cells, columns, strict=False)):
            right = col["align"] == "right"
            x = _PAD + span * (i + 1) - 8 if right else _PAD + span * i + 8
            limit = max(int(span / 7), 4)
            value = cell if len(cell) <= limit else cell[: limit - 1] + "…"
            parts.append(
                _text(x, top, value, 13, theme["text"], weight, "end" if right else "start")
            )

    y += 20
    row([c["name"] for c in columns], y, 650)
    y += 8
    parts.append(
        f'<line x1="{_PAD}" x2="{width - _PAD}" y1="{y:g}" y2="{y:g}" stroke="{theme["border"]}" stroke-width="2"/>'
    )
    for cells in rows:
        y += 22
        row(cells, y, 400)
        parts.append(
            f'<line x1="{_PAD}" x2="{width - _PAD}" y1="{y + 7:g}" y2="{y + 7:g}" stroke="{theme["grid"]}"/>'
        )
    if len(table["rows"]) > len(rows):
        y += 22
        parts.append(_text(16, y, f"… and {len(table['rows']) - len(rows):,} more rows in the interactive table",
                           12, theme["text_secondary"]))  # fmt: skip
    return y + 6


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
