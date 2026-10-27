"""The labelled cases for ``ts.recommend``: our own regression set, not a benchmark.

Each case names the fields a user picked and the chart a careful analyst would draw
today (``best``: the top chart tabsight can already draw), plus, where it differs, the
chart they would draw once every kind exists (``ideal``). The labels were written from
chart-design rules (Few, Cleveland & McGill, the Financial Times visual vocabulary),
not copied from tabsight's output; where the two disagreed, the disagreement was
looked at case by case and the reasoning is in the comment.

The data is synthetic and deterministic so every case is reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    n = 720
    regions = ["North", "South", "East", "West"]
    segments = ["Consumer", "Corporate", "Home Office"]
    products = {
        "Furniture": ["Chairs", "Tables", "Bookcases", "Furnishings"],
        "Technology": ["Phones", "Machines", "Copiers", "Accessories"],
        "Office": ["Paper", "Binders", "Labels", "Storage"],
    }
    category = rng.choice(list(products), n)
    product = [rng.choice(products[c]) for c in category]
    departments = [
        "Customer Experience and Support", "Research and Development Lab",
        "International Partnerships", "Finance and Administration",
        "Marketing Communications Team", "Operations and Logistics",
    ]  # fmt: skip
    countries = [f"Country {chr(65 + i)}{chr(65 + j)}" for i in range(5) for j in range(5)]
    revenue = rng.gamma(2.0, 400.0, n).round(2)
    return pd.DataFrame(
        {
            "Order_ID": [f"ORD-{100000 + i}" for i in range(n)],
            "Order_Date": pd.Timestamp("2019-01-01")
            + pd.to_timedelta(rng.integers(0, 6 * 365, n), "D"),
            "Visit_Date": pd.Timestamp("2024-03-01") + pd.to_timedelta(rng.integers(0, 60, n), "D"),
            "Founded": pd.Timestamp("1990-01-01")
            + pd.to_timedelta(rng.integers(0, 30 * 365, n), "D"),
            "Signup_Date": pd.Timestamp("2023-01-01")
            + pd.to_timedelta(rng.integers(0, 700, n), "D"),
            "Region": rng.choice(regions, n),
            "Segment": rng.choice(segments, n),
            "Channel": rng.choice(["Online", "Store"], n),
            "Category": category,
            "Product": product,
            "Department": rng.choice(departments, n),
            "Country": rng.choice(countries, n),
            "Priority": pd.Categorical(
                rng.choice(["Low", "Medium", "High"], n),
                categories=["Low", "Medium", "High"],
                ordered=True,
            ),
            "Revenue": revenue,
            "Profit": (revenue * rng.normal(0.08, 0.25, n)).round(2),
            "Units": rng.integers(1, 12, n),
            "Discount_Rate": rng.choice([0.0, 0.1, 0.2, 0.3], n),
            "Satisfaction_Score": rng.integers(1, 6, n),
            "Unit_Price": rng.gamma(3.0, 20.0, n).round(2),
        }
    )


# (fields, best today, ideal once every kind exists or None when the same, why)
CASES: list[tuple[dict[str, object], str, str | None, str]] = [
    # --- one measure, nothing to group by
    ({"y": "Revenue"}, "kpi", None, "a single total"),
    ({"y": "Profit"}, "kpi", None, "a single total, negative or not"),
    ({"y": "Units"}, "kpi", None, "a single count"),
    ({"y": "Discount_Rate"}, "kpi", None, "a single average rate"),
    ({"y": "Satisfaction_Score"}, "kpi", None, "a single average score"),
    ({"y": "Unit_Price"}, "kpi", None, "a single average price"),
    # --- two measures, nothing to group by
    ({"y": ["Revenue", "Profit"]}, "table", "scatter", "two totals; how they relate needs rows"),
    ({"y": ["Units", "Unit_Price"]}, "table", "scatter", "two measures"),
    # --- a category and a measure
    ({"x": "Region", "y": "Revenue"}, "bar", None, "4 regions, compare totals"),
    ({"x": "Segment", "y": "Revenue"}, "bar", None, "3 segments"),
    ({"x": "Channel", "y": "Revenue"}, "bar", None, "2 channels"),
    ({"x": "Category", "y": "Units"}, "bar", None, "3 categories, a count"),
    ({"x": "Product", "y": "Revenue"}, "bar", None, "12 short labels still fit upright"),
    ({"x": "Country", "y": "Revenue"}, "hbar", None, "25 categories need horizontal bars"),
    ({"x": "Department", "y": "Revenue"}, "hbar", None, "long labels need horizontal bars"),
    ({"x": "Region", "y": "Profit"}, "bar", None, "profit by region"),
    ({"x": "Product", "y": "Profit"}, "bar", None, "profit by product"),
    ({"x": "Region", "y": "Discount_Rate"}, "bar", None, "average rate per region; never a donut"),
    ({"x": "Product", "y": "Discount_Rate"}, "bar", None, "average rate per product"),
    ({"x": "Segment", "y": "Satisfaction_Score"}, "bar", None, "average score per segment"),
    ({"x": "Department", "y": "Satisfaction_Score"}, "hbar", None, "long labels"),
    ({"x": "Country", "y": "Unit_Price"}, "hbar", None, "25 averages"),
    ({"x": "Priority", "y": "Revenue"}, "bar", None, "ordered category keeps its order"),
    ({"x": "Priority", "y": "Units"}, "bar", None, "ordered category"),
    ({"x": "Order_ID", "y": "Revenue"}, "table", None, "an ID has one row per value; list it"),
    ({"x": "Order_ID", "y": "Units"}, "table", None, "an ID"),
    # --- a date and a measure
    ({"x": "Order_Date", "y": "Revenue"}, "line", None, "six years of revenue: a trend"),
    ({"x": "Order_Date", "y": "Profit"}, "line", None, "profit over time"),
    ({"x": "Order_Date", "y": "Units"}, "line", None, "units over time"),
    ({"x": "Order_Date", "y": "Discount_Rate"}, "line", None, "an average rate over time"),
    ({"x": "Order_Date", "y": "Satisfaction_Score"}, "line", None, "an average score over time"),
    ({"x": "Signup_Date", "y": "Revenue"}, "line", None, "two years by month"),
    ({"x": "Signup_Date", "y": "Units"}, "line", None, "two years by month"),
    ({"x": "Visit_Date", "y": "Revenue"}, "line", None, "60 days by day"),
    ({"x": "Founded", "y": "Revenue"}, "line", None, "30 years by year"),
    ({"x": "Founded", "y": "Unit_Price"}, "line", None, "30 years of averages"),
    # --- a date, a category and a measure
    ({"x": "Order_Date", "y": "Revenue", "color": "Region"}, "multi_line", None, "4 lines"),
    ({"x": "Order_Date", "y": "Revenue", "color": "Segment"}, "multi_line", None, "3 lines"),
    ({"x": "Order_Date", "y": "Revenue", "color": "Channel"}, "multi_line", None, "2 lines"),
    ({"x": "Order_Date", "y": "Profit", "color": "Region"}, "multi_line", None, "profit can be negative; never stacked"),
    ({"x": "Order_Date", "y": "Discount_Rate", "color": "Segment"}, "multi_line", None, "averages don't stack"),
    ({"x": "Order_Date", "y": "Revenue", "color": "Product"}, "multi_line", None, "12 lines: keep the biggest 6"),
    ({"x": "Order_Date", "y": "Revenue", "color": "Country"}, "multi_line", None, "25 lines: keep the biggest 6"),
    ({"x": "Signup_Date", "y": "Units", "color": "Category"}, "multi_line", None, "3 lines by month"),
    ({"x": "Founded", "y": "Revenue", "color": "Region"}, "multi_line", None, "30 years, 4 lines"),
    ({"x": "Region", "y": "Revenue", "color": "Order_Date"}, "multi_line", None, "the date goes on x whichever slot it was put in"),
    # --- two categories and a measure
    ({"x": "Region", "y": "Revenue", "color": "Segment"}, "stacked_bar", None, "totals and their mix"),
    ({"x": "Segment", "y": "Revenue", "color": "Channel"}, "stacked_bar", None, "totals and their mix"),
    ({"x": "Category", "y": "Units", "color": "Region"}, "stacked_bar", None, "a count adds up"),
    # Label changed after review: losses on single orders net out, every Region x Segment
    # total is positive, so stacking is honest here. Product x Segment has negative totals.
    ({"x": "Region", "y": "Profit", "color": "Segment"}, "stacked_bar", None, "all totals positive"),
    ({"x": "Product", "y": "Profit", "color": "Segment"}, "grouped_bar", None, "negative totals don't stack"),
    ({"x": "Product", "y": "Profit", "color": "Channel"}, "grouped_bar", None, "negative totals don't stack"),
    ({"x": "Region", "y": "Discount_Rate", "color": "Segment"}, "grouped_bar", None, "averages don't stack"),
    ({"x": "Segment", "y": "Satisfaction_Score", "color": "Channel"}, "grouped_bar", None, "averages don't stack"),
    # Label changed after hands-on review: we first said "table, ideally a treemap". One bar
    # per product, coloured by its category, shows all 12 with no empty slots.
    ({"x": "Category", "y": "Revenue", "color": "Product"}, "stacked_bar", "treemap", "nested: product bars coloured by category"),
    # Label changed after review: we first said "table, ideally a heatmap". Putting the
    # 4 regions in the colours and the 12 products on x gives a readable stacked bar.
    ({"x": "Region", "y": "Revenue", "color": "Product"}, "stacked_bar", None, "swap: products on x, regions as colours"),
    ({"x": "Country", "y": "Revenue", "color": "Product"}, "table", "heatmap", "a 25 by 12 grid"),
    ({"x": "Product", "y": "Revenue", "color": "Region"}, "stacked_bar", None, "4 colours, 12 bars"),
    ({"x": "Department", "y": "Revenue", "color": "Channel"}, "stacked_bar", None, "2 colours"),
    # --- a category and several measures
    ({"x": "Region", "y": ["Revenue", "Profit"]}, "grouped_bar", None, "same unit side by side"),
    ({"x": "Segment", "y": ["Revenue", "Profit"]}, "grouped_bar", None, "same unit"),
    ({"x": "Region", "y": ["Revenue", "Units"]}, "table", "combo", "money and counts need two axes"),
    ({"x": "Product", "y": ["Revenue", "Discount_Rate"]}, "table", "combo", "money and a rate"),
    ({"x": "Country", "y": ["Revenue", "Profit"]}, "grouped_bar", "scatter", "25 countries: a scatter shows the relation"),
    # --- a date and several measures
    ({"x": "Order_Date", "y": ["Revenue", "Profit"]}, "line", None, "two money lines"),
    ({"x": "Signup_Date", "y": ["Revenue", "Profit"]}, "line", None, "two money lines by month"),
    ({"x": "Order_Date", "y": ["Revenue", "Units"]}, "line", "combo", "different units: two axes"),
    # --- too many fields
    ({"x": ["Region", "Segment", "Channel"], "y": "Revenue"}, "table", None, "three groupings"),
    ({"x": ["Order_Date", "Signup_Date"], "y": "Revenue"}, "table", None, "two dates"),
    # --- no measure
    ({"x": "Region"}, "table", None, "nothing to measure: list the values"),
]  # fmt: skip
