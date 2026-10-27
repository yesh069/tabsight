"""HTML output must be safe with hostile data: no markup injection, no script, no network."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import tabsight as ts
from tabsight.render.html import safe_json
from tabsight.warnings import InvalidSpecError

ROOT = Path(__file__).resolve().parent.parent
EVIL = [
    "<img src=x onerror=alert(1)>",
    "</script><script>alert(2)</script>",
    '"><svg onload=alert(3)>',
    "'; alert(4); '",
    "<!--",
    "  ",
    "{{constructor.constructor('alert(5)')()}}",
    "javascript:alert(6)",
]


@pytest.fixture
def evil_frame() -> pd.DataFrame:
    return pd.DataFrame({"Region": EVIL, "Sales": [float(i + 1) * 10 for i in range(len(EVIL))]})


ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "main", "figure", "figcaption",
                "h1", "h2", "p", "div", "script", "section", "ul", "li", "span"}  # fmt: skip


def _parse(document: str) -> tuple[set[str], list[str]]:
    from html.parser import HTMLParser

    tags: set[str] = set()
    handlers: list[str] = []

    class Collector(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            tags.add(tag)
            handlers.extend(f"{tag}[{name}]" for name, _ in attrs if name.lower().startswith("on"))

    Collector().feed(document)
    return tags, handlers


def _scripts(document: str) -> list[str]:
    return re.findall(r"<script(?: [^>]*)?>(.*?)</script>", document, re.S)


@pytest.mark.parametrize("kind", ["bar", "hbar", "line", "donut", "table", "kpi"])
def test_hostile_values_never_appear_as_markup(evil_frame: pd.DataFrame, kind: str) -> None:
    kw = {"y": "Sales"} if kind == "kpi" else {"x": "Region", "y": "Sales"}
    fig = ts.chart(evil_frame, kind, title=EVIL[0], subtitle=EVIL[2], **kw)
    document = fig.to_html()
    # Parse the page: only tabsight's own tags may exist, and no element may carry an
    # event handler. (Escaped text such as "&lt;img onerror=...&gt;" is harmless.)
    tags, handlers = _parse(document)
    assert tags <= ALLOWED_TAGS, f"{kind}: unexpected tags {tags - ALLOWED_TAGS}"
    assert not handlers, f"{kind}: event-handler attributes {handlers}"
    # Exactly the scripts tabsight wrote: the JSON data block plus its own code.
    blocks = re.findall(r"<script(?: [^>]*)?>", document)
    assert blocks.count('<script type="application/json" id="ts-figure">') == 1
    assert len(blocks) == (2 if kind in ("kpi", "table") else 3) + 1
    # The JSON block round-trips to the original values.
    data = re.search(
        r'<script type="application/json" id="ts-figure">(.*?)</script>', document, re.S
    )
    assert data is not None
    assert "<" not in data.group(1) and ">" not in data.group(1)
    payload = json.loads(data.group(1))
    assert payload["title"] == EVIL[0]


def test_content_security_policy_pins_every_inline_script() -> None:
    fig = ts.chart(pd.DataFrame({"g": ["a", "b"], "v": [1.0, 2.0]}), "bar", x="g", y="v")
    document = fig.to_html()
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', document)
    assert csp is not None
    policy = csp.group(1).replace("&#x27;", "'")
    assert "default-src 'none'" in policy
    assert "connect-src" not in policy  # covered by default-src 'none': no network at all
    assert "unsafe-eval" not in policy and "'unsafe-inline'" not in policy.split("style-src")[0]
    executable = [s for s in _scripts(document) if not s.lstrip().startswith("{")]
    for script in executable:
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        assert f"'sha256-{digest}'" in policy, "an inline script is not pinned by the policy"


def test_cdn_mode_uses_subresource_integrity() -> None:
    fig = ts.chart(pd.DataFrame({"g": ["a"], "v": [1.0]}), "bar", x="g", y="v")
    document = fig.to_html(cdn=True)
    assert 'integrity="sha384-' in document and 'crossorigin="anonymous"' in document
    assert len(document) < 100_000  # ECharts is not inlined


def test_safe_json_escapes_breakout_characters() -> None:
    text = safe_json({"x": "</script><!--   & >"})
    assert "<" not in text and ">" not in text and "&" not in text and " " not in text
    assert json.loads(text) == {"x": "</script><!--   & >"}
    with pytest.raises(ValueError):
        safe_json({"x": float("nan")})


def test_notebook_display_is_sandboxed() -> None:
    fig = ts.chart(pd.DataFrame({"g": EVIL[:2], "v": [1.0, 2.0]}), "bar", x="g", y="v")
    html = fig._repr_html_()
    html = html[html.index("<iframe") :]  # after the still picture, when dukpy is installed
    assert html.startswith('<iframe sandbox="allow-scripts" srcdoc="')
    assert "allow-same-origin" not in html
    assert "<script" not in html.split('srcdoc="', 1)[1]  # the document is attribute-escaped


@pytest.mark.parametrize(
    "patch",
    [
        {"tooltip": {"formatter": "{b}: {c}"}},
        {"series": [{"label": {"formatter": "<b>{b}</b>"}}]},
        {"$fmt": {}},
        {"title": {"text": object()}},
        {"a": float("nan")},
    ],
)
def test_update_refuses_unsafe_patches(patch: dict[str, object]) -> None:
    fig = ts.chart(pd.DataFrame({"g": ["a"], "v": [1.0]}), "bar", x="g", y="v")
    with pytest.raises(InvalidSpecError):
        fig.update(patch)


def test_update_merges_plain_values_without_touching_the_original() -> None:
    fig = ts.chart(pd.DataFrame({"g": ["a"], "v": [1.0]}), "bar", x="g", y="v")
    new = fig.update({"grid": {"left": 40}, "animation": False})
    assert new.option is not None and fig.option is not None
    assert new.option["grid"]["left"] == 40 and new.option["animation"] is False
    assert fig.option["grid"]["left"] == 8


@pytest.mark.node
@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_runtime_escapes_tooltips_and_never_evaluates() -> None:
    script = ROOT / "tests" / "js" / "runtime_unit.cjs"
    runtime = ROOT / "src" / "tabsight" / "render" / "static" / "tabsight.js"
    result = subprocess.run(
        ["node", str(script), str(runtime)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "all runtime checks passed" in result.stdout
