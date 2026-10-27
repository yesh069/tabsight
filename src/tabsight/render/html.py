"""Single-file HTML export.

Security model (see docs/SECURITY_CHECKLIST.md):

- A Content Security Policy allows only the exact inline scripts tabsight wrote (by
  SHA-256 hash) and forbids every network request (``connect-src``, ``img-src`` etc.).
  Even if data somehow reached the page as markup, it could neither run nor send.
- Figure data travels in a ``<script type="application/json">`` block, which browsers
  never execute, with ``<``, ``>``, ``&`` and line separators escaped so no value can
  close the tag.
- Text placed directly in the page (title, captions) goes through ``html.escape``.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
from typing import Any

from tabsight.render.assets import ECHARTS_VERSION, read_static
from tabsight.theme import Theme

__all__ = ["page", "safe_json", "srcdoc_iframe"]

CDN_ECHARTS = f"https://cdn.jsdelivr.net/npm/echarts@{ECHARTS_VERSION}/dist/echarts.min.js"


def safe_json(data: Any) -> str:
    """JSON that is safe inside a <script> block: ASCII only, no '<', '>' or '&'."""
    text = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _sha(text: str, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm, text.encode("utf-8")).digest()
    return f"{algorithm}-{base64.b64encode(digest).decode('ascii')}"


def _css(theme: Theme) -> str:
    return f"""
:root {{ color-scheme: {"dark" if theme.name == "dark" else "light"}; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: {theme.page}; color: {theme.text}; font-family: {theme.font}; }}
.ts-page {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
.ts-tile {{ margin: 0; background: {theme.tile}; border: 1px solid {theme.border};
  border-radius: {theme.radius}px; overflow: hidden; }}
.ts-tile__head {{ padding: 12px 16px 10px; border-bottom: 1px solid {theme.border}; background: {theme.header}; }}
.ts-tile__title {{ margin: 0; font-size: 15px; font-weight: 650; }}
.ts-tile__subtitle {{ margin: 2px 0 0; font-size: 12.5px; color: {theme.text_secondary}; }}
.ts-tile__body {{ padding: 8px 12px 12px; }}
.ts-chart {{ width: 100%; }}
.ts-note {{ margin: 6px 4px 0; font-size: 12px; color: {theme.text_secondary}; }}
.ts-kpi {{ padding: 18px 8px 10px; }}
.ts-kpi__value {{ font-size: 40px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }}
.ts-kpi__label {{ margin-top: 6px; font-size: 13px; color: {theme.text_secondary}; }}
.ts-kpi__detail {{ margin-top: 4px; font-size: 12.5px; color: {theme.text_secondary}; }}
.ts-table-wrap {{ max-height: 520px; overflow: auto; }}
.ts-table {{ width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }}
.ts-table th {{ position: sticky; top: 0; background: {theme.tile}; font-weight: 650;
  border-bottom: 2px solid {theme.border}; padding: 7px 10px; }}
.ts-table td {{ padding: 6px 10px; border-bottom: 1px solid {theme.grid}; }}
.ts-align-right {{ text-align: right; }}
.ts-align-left {{ text-align: left; }}
.ts-tt-head {{ font-weight: 650; margin-bottom: 4px; }}
.ts-tt-row {{ display: flex; align-items: center; gap: 4px; line-height: 1.6; }}
.ts-tt-name {{ flex: 1; padding-right: 12px; }}
.ts-tt-value {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.ts-tt-share {{ margin-left: 8px; color: {theme.text_secondary}; }}
.ts-tt-note {{ color: {theme.text_secondary}; font-size: 11px; }}
.ts-insights {{ margin: 10px 4px 0; padding-top: 8px; border-top: 1px solid {theme.grid}; font-size: 13px; }}
.ts-insights__title {{ margin: 0 0 4px; font-size: 12px; font-weight: 650; color: {theme.text_secondary};
  text-transform: uppercase; letter-spacing: 0.04em; }}
.ts-insights ul {{ margin: 0; padding-left: 18px; line-height: 1.55; overflow-wrap: anywhere; }}
.ts-insights__scope {{ margin-left: 4px; font-size: 11px; color: {theme.text_secondary}; }}
.ts-footer {{ margin-top: 10px; font-size: 11px; color: {theme.text_secondary}; text-align: right; }}
"""


def page(figure: dict[str, Any], theme: Theme, *, cdn: bool = False, lang: str = "en") -> str:
    """A complete, self-contained HTML document for one figure."""
    runtime = read_static("tabsight.js")
    init = (
        "Object.preventExtensions(Object.prototype);"  # no library may add to every object
        "(function(){var d=JSON.parse(document.getElementById('ts-figure').textContent);"
        "tabsight.render(document.getElementById('ts-chart'),d);})();"
    )
    scripts: list[str] = []
    script_src = [f"'{_sha(runtime)}'", f"'{_sha(init)}'"]
    if cdn:
        echarts = read_static("echarts.min.js")
        integrity = _sha(echarts, "sha384")
        scripts.append(
            f'<script src="{CDN_ECHARTS}" integrity="{integrity}" crossorigin="anonymous" '
            'referrerpolicy="no-referrer"></script>'
        )
        script_src.append("https://cdn.jsdelivr.net")
    elif figure["kind"] not in ("kpi", "table"):
        echarts = read_static("echarts.min.js")
        scripts.append(f"<script>{echarts}</script>")
        script_src.append(f"'{_sha(echarts)}'")
    if figure.get("maps"):
        topojson = read_static("topojson-client.min.js")  # turns the bundled TopoJSON into GeoJSON
        scripts.append(f"<script>{topojson}</script>")
        script_src.append(f"'{_sha(topojson)}'")
    scripts.append(f"<script>{runtime}</script>")
    scripts.append(f"<script>{init}</script>")
    csp = (
        "default-src 'none'; "
        f"script-src {' '.join(script_src)}; "
        "style-src 'unsafe-inline'; "  # ECharts tooltips use style attributes
        "img-src data: blob:; "
        "base-uri 'none'; form-action 'none'"
    )
    title = figure.get("title") or "tabsight"
    subtitle = figure.get("subtitle")
    notes = figure.get("notes") or []
    height = int(figure.get("height") or 420)
    head = f'<h1 class="ts-tile__title">{html.escape(title)}</h1>'
    if subtitle:
        head += f'<p class="ts-tile__subtitle">{html.escape(subtitle)}</p>'
    note_html = "".join(f'<p class="ts-note">{html.escape(n)}</p>' for n in notes)
    found = figure.get("insights") or []
    if found:
        note_html += (
            '<section class="ts-insights" aria-label="Insights"><h2 class="ts-insights__title">Insights</h2><ul>'
            + "".join(
                f'<li>{html.escape(i["text"])} <span class="ts-insights__scope">{html.escape(i["scope"])}</span></li>'
                for i in found
            )
            + "</ul></section>"
        )
    chart_style = f' style="height:{height}px"' if figure["kind"] not in ("kpi", "table") else ""
    return (
        "<!doctype html>\n"
        f'<html lang="{html.escape(lang)}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp)}">\n'
        '<meta name="referrer" content="no-referrer">\n'
        '<meta name="generator" content="tabsight">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_css(theme)}</style>\n</head>\n<body>\n"
        '<main class="ts-page">\n<figure class="ts-tile">\n'
        f'<figcaption class="ts-tile__head">{head}</figcaption>\n'
        f'<div class="ts-tile__body"><div id="ts-chart" class="ts-chart"{chart_style} '
        f'role="img" aria-label="{html.escape(title)}"></div>{note_html}</div>\n'
        "</figure>\n"
        '<p class="ts-footer">Made with tabsight</p>\n</main>\n'
        f'<script type="application/json" id="ts-figure">{safe_json(figure)}</script>\n'
        + "\n".join(scripts)
        + "\n</body>\n</html>\n"
    )


def srcdoc_iframe(document: str, height: int) -> str:
    """Embed a document in a sandboxed iframe (scripts allowed, no access to the host page)."""
    return (
        f'<iframe sandbox="allow-scripts" srcdoc="{html.escape(document, quote=True)}" '
        f'style="width:100%;height:{int(height)}px;border:0" title="tabsight chart"></iframe>'
    )
