"""Render the chart images used in README.md (real tabsight output, drawn by ECharts in Node).

Usage: python tools/make_readme_images.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tabsight as ts  # noqa: E402

OUT = ROOT / "docs" / "assets" / "examples"
IMAGES: dict[str, dict[str, object]] = {
    "sales-by-region": {"kind": "bar", "x": "Region", "y": "Sales"},
    "sales-by-quarter": {
        "kind": "multi_line",
        "x": "Order_Date",
        "y": "Sales",
        "color": "Region",
        "freq": "quarter",
    },
    "category-mix": {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Segment"},
    "sub-category-share": {"kind": "donut", "x": "Sub_Category", "y": "Sales"},
    "sales-by-state-map": {"kind": "map", "geo": "State", "y": "Sales"},
    "sales-treemap": {"kind": "treemap", "x": ["Category", "Sub_Category"], "y": "Sales"},
    "region-panels": {
        "kind": "stacked_bar",
        "x": "Category",
        "y": "Sales",
        "color": "Segment",
        "facet": "Region",
    },
}


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node.js is needed to render the images")
    OUT.mkdir(parents=True, exist_ok=True)
    orders = ts.load(ROOT / "examples" / "superstore_sample.csv")
    with tempfile.TemporaryDirectory() as tmp, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name, kw in IMAGES.items():
            fig = ts.chart(orders, **kw)  # type: ignore[arg-type]
            data = Path(tmp) / f"{name}.json"
            data.write_text(json.dumps(fig.to_dict()), encoding="utf-8")
            subprocess.run(  # noqa: S603 - fixed local script and paths
                [
                    node,
                    str(ROOT / "tools" / "figure_svg.cjs"),
                    str(ROOT),
                    str(data),
                    str(OUT / f"{name}.svg"),
                    "760",
                    str(fig.height) if "facet" in kw else "360",  # panels need their own height
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
