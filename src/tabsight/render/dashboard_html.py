"""Single-file HTML for dashboards. Same security model as ``render/html.py``:

- a Content Security Policy that allows only the exact inline scripts written here (by
  SHA-256 hash) and no network requests;
- the dashboard payload travels in a ``<script type="application/json">`` block with
  ``<``, ``>`` and ``&`` escaped, so no value can close the tag;
- text placed in the page by Python (title, insights) goes through ``html.escape``; the
  runtime builds everything else with ``textContent``.
"""

from __future__ import annotations

import html
from typing import Any

from tabsight.render.assets import read_static
from tabsight.render.html import CDN_ECHARTS, _css, _sha, safe_json
from tabsight.theme import Theme

__all__ = ["dashboard_page"]


def _dash_css(theme: Theme) -> str:
    return f"""
.ts-dash {{ max-width: 1400px; margin: 0 auto; padding: 20px 16px 28px; }}
.ts-dash__title {{ margin: 0; font-size: 22px; font-weight: 700; }}
.ts-dash__subtitle {{ margin: 4px 0 0; color: {theme.text_secondary}; font-size: 13.5px; }}
.ts-filters {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin: 16px 0 8px; }}
.ts-filter {{ display: flex; align-items: center; gap: 6px; font-size: 13px; }}
.ts-filter__name {{ font-weight: 600; }}
.ts-filter select, .ts-filter summary {{ font: inherit; color: {theme.text}; background: {theme.tile};
  border: 1px solid {theme.border}; border-radius: 6px; padding: 5px 8px; cursor: pointer; }}
.ts-filter__menu {{ position: relative; }}
.ts-filter__menu[open] summary {{ border-color: {theme.accent}; }}
.ts-filter__list {{ position: absolute; z-index: 10; top: 34px; left: 0; min-width: 200px; max-height: 300px;
  overflow: auto; background: {theme.tile}; border: 1px solid {theme.border}; border-radius: 6px; padding: 6px 4px;
  box-shadow: 0 6px 20px rgba(0,0,0,.12); }}
.ts-filter__item {{ display: block; padding: 3px 8px; white-space: nowrap; cursor: pointer; }}
.ts-chips {{ display: flex; flex-wrap: wrap; gap: 6px; min-height: 30px; align-items: center; margin-bottom: 10px; }}
.ts-chip {{ display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; background: {theme.header};
  border: 1px solid {theme.border}; border-radius: 999px; padding: 2px 4px 2px 10px; }}
.ts-chip__x, .ts-reset, .ts-tile__csv {{ font: inherit; color: {theme.text_secondary}; background: none; border: 0;
  cursor: pointer; border-radius: 999px; }}
.ts-chip__x {{ width: 22px; height: 22px; font-size: 15px; line-height: 1; }}
.ts-reset {{ font-size: 12.5px; text-decoration: underline; padding: 2px 6px; }}
.ts-grid {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; }}
.ts-dash-tile {{ min-width: 0; }}
.ts-dash-tile .ts-tile__head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; }}
.ts-dash-tile .ts-tile__title {{ font-size: 14px; flex: 1; }}
.ts-dash-tile .ts-tile__subtitle {{ flex-basis: 100%; order: 3; }}
.ts-tile__csv {{ font-size: 11.5px; padding: 2px 6px; }}
.ts-tile__csv:hover, .ts-chip__x:hover, .ts-reset:hover {{ color: {theme.text}; background: {theme.grid}; }}
.ts-tile__status {{ margin: 4px 4px 0; font-size: 11px; color: {theme.text_secondary}; min-height: 0; }}
.ts-tile__status:empty {{ display: none; }}
.ts-dash-insights {{ margin-top: 14px; }}
:focus-visible {{ outline: 2px solid {theme.accent}; outline-offset: 2px; }}
@media (max-width: 760px) {{ .ts-dash-tile {{ grid-column: span 12 !important; }} }}
@media print {{ .ts-filters, .ts-tile__csv, .ts-reset, .ts-chip__x {{ display: none; }}
  .ts-dash-tile {{ break-inside: avoid; }} }}
"""


def dashboard_page(
    payload: dict[str, Any], theme: Theme, *, cdn: bool = False, lang: str = "en"
) -> str:
    runtime = read_static("tabsight.js")
    dash = read_static("dashboard.js")
    init = (
        "(function(){var d=JSON.parse(document.getElementById('ts-dashboard').textContent);"
        "tabsightDashboard.mount(document.getElementById('ts-dash-root'),d);})();"
    )
    scripts: list[str] = []
    script_src = [f"'{_sha(runtime)}'", f"'{_sha(dash)}'", f"'{_sha(init)}'"]
    echarts = read_static("echarts.min.js")
    if cdn:
        scripts.append(
            f'<script src="{CDN_ECHARTS}" integrity="{_sha(echarts, "sha384")}" crossorigin="anonymous" '
            'referrerpolicy="no-referrer"></script>'
        )
        script_src.append("https://cdn.jsdelivr.net")
    else:
        scripts.append(f"<script>{echarts}</script>")
        script_src.append(f"'{_sha(echarts)}'")
    if any(t["figure"].get("maps") for t in payload["tiles"]):
        topojson = read_static("topojson-client.min.js")
        scripts.append(f"<script>{topojson}</script>")
        script_src.append(f"'{_sha(topojson)}'")
    scripts += [
        f"<script>{runtime}</script>",
        f"<script>{dash}</script>",
        f"<script>{init}</script>",
    ]
    csp = (
        "default-src 'none'; "
        f"script-src {' '.join(script_src)}; "
        "style-src 'unsafe-inline'; "
        "img-src data: blob:; "
        "base-uri 'none'; form-action 'none'"
    )
    title = payload.get("title") or "tabsight dashboard"
    head = f'<h1 class="ts-dash__title">{html.escape(title)}</h1>'
    if payload.get("subtitle"):
        head += f'<p class="ts-dash__subtitle">{html.escape(payload["subtitle"])}</p>'
    found = payload.get("insights") or []
    insights = ""
    if found:
        items = "".join(f"<li>{html.escape(i['text'])}</li>" for i in found)
        insights = (
            '<section class="ts-tile ts-dash-insights" aria-label="Insights"><div class="ts-tile__body">'
            '<div class="ts-insights"><h2 class="ts-insights__title">Insights</h2>'
            f"<ul>{items}</ul>"
            f'<p class="ts-insights__scope ts-dash-insights__scope">{html.escape(payload["words"]["all_data"])}</p>'
            "</div></div></section>"
        )
    return (
        "<!doctype html>\n"
        f'<html lang="{html.escape(lang)}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp)}">\n'
        '<meta name="referrer" content="no-referrer">\n'
        '<meta name="generator" content="tabsight">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_css(theme)}{_dash_css(theme)}</style>\n</head>\n<body>\n"
        f'<main class="ts-dash">\n<header>{head}</header>\n<div id="ts-dash-root"></div>\n{insights}\n'
        '<p class="ts-footer">Made with tabsight</p>\n</main>\n'
        f'<script type="application/json" id="ts-dashboard">{safe_json(payload)}</script>\n'
        + "\n".join(scripts)
        + "\n</body>\n</html>\n"
    )
