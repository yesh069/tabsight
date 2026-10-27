"""The documentation must never lie: run every example and check every reference table."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

import tabsight as ts
from tabsight.formats import LOCALES, format_date
from tabsight.formulas import FUNCTIONS
from tabsight.spec import ALIASES, CHART_KINDS

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.rglob("*.md"))
PAGES_WITH_CODE = [
    p for p in [*PAGES, ROOT / "README.md"] if "```python" in p.read_text(encoding="utf-8")
]

sys.path.insert(0, str(ROOT / "tools"))
import render_doc_outputs  # noqa: E402 - tools/ is not a package


@pytest.mark.parametrize("page", PAGES_WITH_CODE, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_examples_run_and_shown_output_is_current(page: Path) -> None:
    """Every example runs, and every 'Output' block shows exactly what the code prints.

    If this fails after a change, run: python tools/render_doc_outputs.py
    """
    render_doc_outputs._setup()
    old = Path.cwd()
    os.chdir(ROOT)
    try:
        text = page.read_text(encoding="utf-8")
        rendered = render_doc_outputs.render(text, page.relative_to(ROOT).as_posix())
    finally:
        os.chdir(old)
        ts.settings.reset_defaults()
    if int(pd.__version__.split(".")[0]) < 3:
        return  # examples ran; exact output is defined by pandas 3 (pandas 2 prints some types differently)
    assert rendered == text, (
        f"{page.relative_to(ROOT).as_posix()}: shown output is out of date; run python tools/render_doc_outputs.py"
    )


def test_pages_with_code_show_real_output() -> None:
    """The guide shows results, not just code (TensorFlow/Polars style)."""
    for page in (DOCS / "guide").glob("*.md"):
        text = page.read_text(encoding="utf-8")
        if "```python" in text:
            assert '```text title="Output"' in text, f"{page.name} shows no output"


def _normalise(text: str) -> str:
    return text.replace(" ", " ").replace(" ", " ")


def test_locale_table_matches_the_code() -> None:
    page = (DOCS / "reference" / "locales.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| `(\w+)` \| `(\w+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| ([^|]+) \|$", page, re.M
    )
    assert {r[0] for r in rows} == set(LOCALES), "every locale must be documented"
    for code, currency, money, number, compact, date in rows:
        assert (
            _normalise(
                ts.format_number(1234.5, "currency", locale=code, currency=currency, decimals=2)
            )
            == money
        )
        assert _normalise(ts.format_number(123456.7, "number", locale=code, decimals=1)) == number
        assert (
            _normalise(
                ts.format_number(2_300_000, "currency", "compact", locale=code, currency=currency)
            )
            == compact
        )
        assert format_date(pd.Timestamp("2017-01-05"), "day", locale=code) == date.strip()


def test_every_formula_function_is_documented() -> None:
    page = (DOCS / "reference" / "formula-functions.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Z]+)\(", page))
    assert set(FUNCTIONS) <= documented, f"undocumented: {sorted(set(FUNCTIONS) - documented)}"
    assert documented <= set(FUNCTIONS), (
        f"documented but missing: {sorted(documented - set(FUNCTIONS))}"
    )


def test_every_chart_kind_is_documented() -> None:
    page = (DOCS / "reference" / "chart-kinds.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\|[^|]*\| `(\w+)` \|", page, re.M))
    assert documented == set(CHART_KINDS)
    for alias in ALIASES:
        assert f"`{alias}`" in page


def test_every_lint_rule_is_documented() -> None:
    from tabsight.lint import RULES

    page = (DOCS / "reference" / "lint-rules.md").read_text(encoding="utf-8")
    documented = dict(re.findall(r"^\| `(\w+)` \| (\w+) \|", page, re.M))
    assert documented == {code: severity for code, (severity, _) in RULES.items()}


def test_every_setting_is_documented() -> None:
    page = (DOCS / "guide" / "settings.md").read_text(encoding="utf-8")
    import dataclasses

    for field in dataclasses.fields(ts.Settings):
        assert f"| `{field.name}` |" in page, field.name


def test_every_check_code_is_documented() -> None:
    page = (DOCS / "guide" / "checking.md").read_text(encoding="utf-8")
    source = (ROOT / "src" / "tabsight" / "check.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'Issue\(\s*"\w+",\s*"(\w+)"', source))
    assert codes, "found no issue codes"
    for code in codes:
        assert f"`{code}`" in page, code


def test_internal_links_point_to_real_pages() -> None:
    link = re.compile(r"\]\(((?!https?://|#)[^)#]+\.md)(?:#[^)]*)?\)")
    broken = []
    for page in PAGES:
        for target in link.findall(page.read_text(encoding="utf-8")):
            if not (page.parent / target).resolve().exists():
                broken.append(f"{page.relative_to(DOCS)} -> {target}")
    assert not broken, broken


def test_mkdocs_nav_lists_every_page() -> None:
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for page in PAGES:
        rel = page.relative_to(DOCS).as_posix()
        if rel == "README.md":
            continue  # GitHub index of the docs folder
        assert rel in nav, f"{rel} is not in mkdocs.yml nav"


def test_readme_images_are_valid_svg() -> None:
    from defusedxml import minidom  # never parse XML with the standard library

    images = sorted((DOCS / "assets" / "examples").glob("*.svg"))
    assert len(images) >= 4
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for image in images:
        minidom.parse(str(image))  # broken quoting in an attribute would fail here
        assert f"docs/assets/examples/{image.name}" in readme


def test_readme_links_point_to_real_files() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(((?!https?://|#)[^)#]+)", readme):
        assert (ROOT / target).exists(), target
