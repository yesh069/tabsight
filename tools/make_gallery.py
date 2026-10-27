"""Write every chart kind tabsight can draw into one folder, with an index page.

Usage: python tools/make_gallery.py [output folder]   (default: ./gallery, git-ignored)
"""

from __future__ import annotations

import html
import math
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import tabsight as ts  # noqa: E402

CHARTS: list[tuple[str, str, dict[str, object]]] = [
    # comparison
    ("bar", "Bars, largest first, values on the bars", {"kind": "bar", "x": "Region", "y": "Sales"}),
    ("hbar", "Horizontal bars", {"kind": "hbar", "x": "City", "y": "Sales"}),
    ("grouped-bar", "Grouped bars", {"kind": "grouped_bar", "x": "Region", "y": "Sales", "color": "Segment"}),
    ("lollipop", "Lollipop", {"kind": "lollipop", "x": "Sub_Category", "y": "Sales"}),
    ("bullet", "Bullet: actual against a goal", {"data": "targets", "kind": "bullet", "x": "Rep", "y": "Sales", "goal": "Target"}),
    # part to whole
    ("stacked-bar", "Stacked bars", {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Region"}),
    ("stacked100-bar", "100% stacked bars", {"kind": "stacked100_bar", "x": "Region", "y": "Sales", "color": "Segment"}),
    ("donut", "Donut: 7 slices plus a grey Other", {"kind": "donut", "x": "Sub_Category", "y": "Sales"}),
    ("treemap", "Treemap: category, then sub-category", {"kind": "treemap", "x": ["Category", "Sub_Category"], "y": "Sales"}),
    ("sunburst", "Sunburst: three levels", {"kind": "sunburst", "x": ["Region", "Category", "Sub_Category"], "y": "Sales"}),
    ("waterfall", "Waterfall: from revenue to profit", {"data": "bridge", "kind": "waterfall", "x": "Step", "y": "Amount"}),
    ("funnel", "Funnel with conversion in the tooltip", {"data": "funnel", "kind": "funnel", "x": "Stage", "y": "Users"}),
    # trend
    ("line", "Monthly line, never smoothed", {"kind": "line", "x": "Order_Date", "y": "Sales", "freq": "month"}),
    ("multi-line", "One line per region (with the incomplete-quarter note)",
     {"kind": "multi_line", "x": "Order_Date", "y": "Sales", "color": "Region", "freq": "quarter"}),
    ("area", "Area", {"kind": "area", "x": "Order_Date", "y": "Profit", "freq": "month"}),
    ("stacked-area", "Stacked area", {"kind": "stacked_area", "x": "Order_Date", "y": "Sales", "color": "Category", "freq": "quarter"}),
    ("combo", "Combo: bars and a line on two axes", {"kind": "combo", "x": "Order_Date", "y": ["Sales", "Quantity"], "freq": "quarter"}),
    ("sparkline", "Sparkline", {"kind": "sparkline", "x": "Order_Date", "y": "Sales", "freq": "month"}),
    ("calendar", "Calendar heatmap", {"data": "days", "kind": "calendar_heatmap", "x": "Day", "y": "Visits"}),
    ("sine", "A line over a number: a real value axis", {"data": "sine", "kind": "line", "x": "angle", "y": "sine"}),
    # flow, relationship, distribution
    ("sankey", "Sankey: segment to category", {"kind": "sankey", "source": "Segment", "target": "Category", "y": "Sales"}),
    ("scatter", "Scatter: one dot per order", {"kind": "scatter", "x": "Sales", "y": "Profit", "color": "Category"}),
    ("bubble", "Bubble: one per sub-category", {"kind": "bubble", "x": "Sub_Category", "y": ["Sales", "Profit", "Quantity"]}),
    ("heatmap", "Heatmap with diverging colours", {"kind": "heatmap", "x": "Order_Date", "color": "Category", "y": "Profit", "freq": "quarter"}),
    ("histogram", "Histogram", {"kind": "histogram", "x": "Sales"}),
    ("boxplot", "Box plot by category", {"kind": "boxplot", "x": "Category", "y": "Profit"}),
    # ranking and single values
    ("pareto", "Pareto: bars and the running share", {"kind": "pareto", "x": "Sub_Category", "y": "Sales"}),
    ("kpi", "KPI card", {"kind": "kpi", "y": "Sales"}),
    ("gauge", "Gauge against a goal", {"kind": "gauge", "y": "Sales", "goal": 300000}),
    ("table", "Table with grouped parents", {"kind": "table", "x": ["Category", "Sub_Category"], "y": ["Sales", "Profit", "Discount"]}),
    # maps
    ("choropleth", "Map: US states, found automatically", {"kind": "choropleth", "geo": "State", "y": "Sales"}),
    ("symbol-map", "Symbol map: cities", {"kind": "symbol_map", "geo": "City", "y": "Sales"}),
    ("density-map", "Density map", {"kind": "density_map", "geo": "City", "y": "Sales"}),
    ("flow-map", "Flow map: trade between countries", {"data": "trade", "kind": "flow_map", "source": "Exporter", "target": "Importer", "y": "Value"}),
    # small multiples and themes
    ("facet-bars", "Small multiples: one panel per region, one scale", {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Segment", "facet": "Region"}),
    ("facet-map", "Small multiples of maps", {"kind": "map", "geo": "State", "y": "Sales", "facet": "Category"}),
    ("bar-dark", "Dark theme", {"kind": "stacked_bar", "x": "Category", "y": "Sales", "color": "Region", "theme": "dark"}),
    ("bar-euro", "German locale, euros", {"kind": "bar", "x": "Region", "y": "Sales", "locale": "de_DE", "currency": "EUR"}),
]  # fmt: skip


def extra_data() -> dict[str, pd.DataFrame]:
    """Small made-up tables for the kinds the orders sample can't show well."""
    rng = np.random.default_rng(1)
    x = np.arange(0, math.pi * 2, 0.05)
    return {
        "targets": pd.DataFrame({"Rep": ["Ann", "Bo", "Cy", "Di"], "Sales": [120.0, 95, 70, 140],
                                 "Target": [100.0, 100, 90, 120]}),
        "bridge": pd.DataFrame({"Step": ["Revenue", "Cost of sales", "Marketing", "Salaries", "Grants", "Tax"],
                                "Amount": [1000.0, -420, -180, -350, 60, -45]}),
        "funnel": pd.DataFrame({"Stage": ["Visited", "Signed up", "Trial", "Paid"], "Users": [12000, 3400, 1500, 420]}),
        "days": pd.DataFrame({"Day": pd.date_range("2023-01-01", "2024-12-31"),
                              "Visits": rng.poisson(200, 731) * (1 + 0.3 * np.sin(np.arange(731) / 58))}),
        "sine": pd.DataFrame({"angle": x, "sine": np.sin(x)}),
        "trade": pd.DataFrame({"Exporter": ["China", "China", "Germany", "United States", "India", "Brazil"],
                               "Importer": ["United States", "Germany", "France", "Mexico", "United Kingdom", "China"],
                               "Value": [500, 220, 180, 260, 90, 150.0]}),
    }  # fmt: skip


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
        extra = extra_data()
        for slug, caption, kw in CHARTS:
            kw = dict(kw)
            data = extra[str(kw.pop("data"))] if "data" in kw else orders
            fig = ts.chart(data, **kw)  # type: ignore[arg-type]
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
<p>All 33 chart kinds and small multiples, on the synthetic sample data ({len(orders):,} orders). Each chart is one offline HTML file.</p></header>
<ul>
{rows}
</ul></body></html>
""",
        encoding="utf-8",
    )
    print(f"wrote {len(items)} charts and index.html to {out}")


if __name__ == "__main__":
    main()
