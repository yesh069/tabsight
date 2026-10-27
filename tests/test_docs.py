"""The documentation must never lie: run every example and check every reference table."""

from __future__ import annotations

import os
import re
import warnings
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
FENCE = re.compile(r"^```python\n(.*?)^```", re.M | re.S)


def python_blocks(page: Path) -> list[str]:
    blocks = FENCE.findall(page.read_text(encoding="utf-8"))
    return [b for b in blocks if not b.lstrip().startswith("# not run")]


PAGES_WITH_CODE = [p for p in PAGES if python_blocks(p)]


@pytest.mark.parametrize("page", PAGES_WITH_CODE, ids=lambda p: str(p.relative_to(DOCS)))
def test_every_example_runs(page: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Run a page's examples in order, in one namespace, from the repository root."""
    namespace: dict[str, object] = {"__name__": "__docs__"}
    old = Path.cwd()
    os.chdir(ROOT)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i, block in enumerate(python_blocks(page), 1):
                try:
                    exec(compile(block, f"{page.name} block {i}", "exec"), namespace)
                except Exception as err:  # pragma: no cover - reported as a failure
                    pytest.fail(
                        f"{page.relative_to(DOCS)} example {i} failed: {type(err).__name__}: {err}\n{block}"
                    )
    finally:
        os.chdir(old)
        ts.settings.reset_defaults()


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
