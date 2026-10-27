"""Write every chart kind tabsight can draw into one folder, with an index page.

Usage: python tools/make_gallery.py [output folder]   (default: ./gallery, git-ignored)
"""

from __future__ import annotations

import html
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

import tabsight as ts  # noqa: E402

CHARTS: list[tuple[str, str, dict[str, object]]] = [
    ("bar", "Bars, largest first, values on the bars", {"kind": "bar", "x": "Region", "y": "Sales"}),
    ("bar-many", "13 categories: labels rotated, none skipped", {"kind": "bar", "x": "Sub_Category", "y": "Profit"}),
    ("hbar", "Horizontal bars", {"kind": "hbar", "x": "City", "y": "Sales"}),
    ("grouped-bar", "Grouped bars", {"kind": "grouped_bar", "x": "Region", "y": "Sales", "color": "Segment"}),
    ("stacked-bar", "Stacked bars", {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Region"}),
    ("stacked100-bar", "100% stacked bars", {"kind": "stacked100_bar", "x": "Region", "y": "Sales", "color": "Segment"}),
    ("line", "Monthly line, never smoothed", {"kind": "line", "x": "Order_Date", "y": "Sales", "freq": "month"}),
    ("multi-line", "One line per region (with the incomplete-quarter note)",
     {"kind": "multi_line", "x": "Order_Date", "y": "Sales", "color": "Region", "freq": "quarter"}),
    ("area", "Area", {"kind": "area", "x": "Order_Date", "y": "Profit", "freq": "month"}),
    ("stacked-area", "Stacked area", {"kind": "stacked_area", "x": "Order_Date", "y": "Sales", "color": "Category", "freq": "quarter"}),
    ("sparkline", "Sparkline", {"kind": "sparkline", "x": "Order_Date", "y": "Sales", "freq": "month"}),
    ("donut", "Donut: 7 slices plus a grey Other", {"kind": "donut", "x": "Sub_Category", "y": "Sales"}),
    ("kpi", "KPI card", {"kind": "kpi", "y": "Sales"}),
    ("table", "Table with grouped parents", {"kind": "table", "x": ["Category", "Sub_Category"], "y": ["Sales", "Profit", "Discount"]}),
    ("bar-dark", "Dark theme", {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Region", "theme": "dark"}),
    ("bar-euro", "German locale, euros", {"kind": "bar", "x": "Region", "y": "Sales", "locale": "de_DE", "currency": "EUR"}),
]  # fmt: skip

HOSTILE = pd.DataFrame(
    {"Region": ["<img src=x onerror=alert(1)>", "</script><script>alert(2)</script>", '"><svg onload=alert(3)>'],
     "Sales": [30.0, 20.0, 10.0]}
)  # fmt: skip


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "gallery"
    out.mkdir(parents=True, exist_ok=True)
    orders = ts.load(ROOT / "examples" / "superstore_sample.csv")
    items = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for slug, caption, kw in CHARTS:
            fig = ts.chart(orders, **kw)  # type: ignore[arg-type]
            fig.to_html(out / f"{slug}.html")
            items.append((slug, caption, fig.title))
        hostile = ts.chart(
            HOSTILE, "bar", x="Region", y="Sales", title="<b>bold?</b> <img src=x onerror=alert(9)>"
        )
        hostile.to_html(out / "hostile-data.html")
        items.append(
            ("hostile-data", "Security check: hostile values shown as plain text", hostile.title)
        )
    rows = "\n".join(
        f'<li><a href="{slug}.html">{html.escape(title)}</a><span>{html.escape(caption)}</span></li>'
        for slug, caption, title in items
    )
    (out / "index.html").write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>tabsight chart gallery</title>
<style>
body {{ margin: 0; font-family: "Segoe UI", -apple-system, Roboto, Arial, sans-serif; background: #f4f6f9; color: #1f2329; }}
header {{ background: #1f3b5c; color: #fff; padding: 28px 24px 22px; border-bottom: 4px solid #f28e2b; }}
header h1 {{ margin: 0 0 6px; font-size: 24px; }} header p {{ margin: 0; color: #cdd7e2; font-size: 14px; }}
ul {{ list-style: none; margin: 24px auto; padding: 0 16px; max-width: 760px; }}
li {{ background: #fff; border: 1px solid #e1e5ea; border-radius: 6px; margin-bottom: 8px; padding: 12px 16px; }}
a {{ font-weight: 650; color: #1d5fa3; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
span {{ display: block; margin-top: 2px; font-size: 13px; color: #5f6670; }}
</style></head><body>
<header><h1>tabsight chart gallery</h1>
<p>Phase 3 charts on the synthetic sample data ({len(orders):,} orders). Each chart is one offline HTML file.</p></header>
<ul>
{rows}
</ul></body></html>
""",
        encoding="utf-8",
    )
    print(f"wrote {len(items)} charts and index.html to {out}")


if __name__ == "__main__":
    main()
