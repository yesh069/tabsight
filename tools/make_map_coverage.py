"""Write docs/reference/map-coverage.md from the bundled map data.

The top-30 table compares the bundled region counts with official lists (kept in
tests/test_geo.py, where a test checks them); the full table lists every country.
Usage: python tools/make_map_coverage.py [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.test_geo import OFFICIAL  # noqa: E402

import tabsight as ts  # noqa: E402

PAGE = ROOT / "docs" / "reference" / "map-coverage.md"


def render() -> str:
    table = ts.geo.coverage()
    names = dict(zip(table["code"], table["country"], strict=True))
    lines = [
        "# Map coverage",
        "",
        "What the bundled maps contain. The data is Natural Earth "
        f"{ts.geo.version()['natural_earth']} (public domain), simplified for the web. This page is "
        "generated from the data by `tools/make_map_coverage.py`, and a test fails if it is out of date.",
        "",
        "## The 30 most-used countries, checked",
        "",
        "Each was compared with its official list of first-level regions. **Layer** is the one whose "
        "count is compared; see [maps](../guide/maps.md#layers-the-regions-people-actually-use) for what "
        "layers are.",
        "",
        "| Country | Layer | Official | Bundled | Notes |",
        "|---------|-------|---------:|--------:|-------|",
    ]
    for (code, layer), (official, bundled, why) in OFFICIAL.items():
        lines.append(f"| {names[code]} (`{code}`) | `{layer}` | {official} | {bundled} | {why} |")
    lines += [
        "",
        "## Every country",
        "",
        "**Regions** counts Natural Earth's level 1 (`admin1`); other layers are listed after it.",
        "",
        "| Country | Code | Regions | Region type | Layers |",
        "|---------|------|--------:|-------------|--------|",
    ]
    for row in table.itertuples(index=False):
        lines.append(
            f"| {row.country} | `{row.code}` | {row.regions} | {row.region_type or ''} | {row.layers} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    text = render()
    if "--check" in sys.argv:
        if PAGE.read_text(encoding="utf-8") != text:
            raise SystemExit(
                "docs/reference/map-coverage.md is out of date: run python tools/make_map_coverage.py"
            )
        return
    PAGE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
