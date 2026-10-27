"""Create examples/superstore_sample.csv: a synthetic, Superstore-shaped dataset.

It is generated (not the real Superstore file), so it can be shipped and used freely in
the documentation and tests. Fixed seed: the file is identical on every run.

Usage: python tools/make_sample_data.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "superstore_sample.csv"

REGIONS = {
    "West": [("California", "Los Angeles"), ("Washington", "Seattle"), ("Oregon", "Portland")],
    "East": [("New York", "New York City"), ("Pennsylvania", "Philadelphia"), ("Ohio", "Columbus")],
    "Central": [("Texas", "Houston"), ("Illinois", "Chicago"), ("Michigan", "Detroit")],
    "South": [("Florida", "Miami"), ("Georgia", "Atlanta"), ("Virginia", "Richmond")],
}
CATEGORIES = {
    "Furniture": ["Chairs", "Tables", "Bookcases", "Furnishings"],
    "Office Supplies": ["Binders", "Paper", "Storage", "Art", "Labels"],
    "Technology": ["Phones", "Copiers", "Accessories", "Machines"],
}
SHIP_MODES = ["Standard Class", "Second Class", "First Class", "Same Day"]


def main() -> None:
    rng = np.random.default_rng(2017)
    rows = 1200
    region = rng.choice(list(REGIONS), rows, p=[0.32, 0.29, 0.23, 0.16])
    place = [REGIONS[r][rng.integers(0, 3)] for r in region]
    category = rng.choice(list(CATEGORIES), rows, p=[0.21, 0.6, 0.19])
    sub = [rng.choice(CATEGORIES[c]) for c in category]
    days = np.sort(rng.integers(0, 4 * 365, rows))
    # Seasonality: more orders late in the year.
    order_date = pd.Timestamp("2014-01-03") + pd.to_timedelta(days, unit="D")
    ship_date = order_date + pd.to_timedelta(rng.integers(0, 7, rows), unit="D")
    base = {"Furniture": 350.0, "Office Supplies": 120.0, "Technology": 420.0}
    sales = np.round([rng.gamma(2.0, base[c] / 2) for c in category], 2)
    discount = rng.choice([0.0, 0.0, 0.0, 0.1, 0.2, 0.3, 0.5], rows)
    margin = rng.normal(0.17, 0.12, rows) - discount * 0.9
    profit = np.round(sales * margin, 2)
    customers = [f"CU-{n:05d}" for n in rng.integers(10000, 10800, rows)]
    frame = pd.DataFrame(
        {
            "Row_ID": np.arange(1, rows + 1),
            "Order_ID": [f"US-{d.year}-{100000 + i:06d}" for i, d in enumerate(order_date)],
            "Order_Date": order_date.strftime("%m/%d/%Y"),
            "Ship_Date": ship_date.strftime("%m/%d/%Y"),
            "Ship_Mode": rng.choice(SHIP_MODES, rows, p=[0.6, 0.2, 0.15, 0.05]),
            "Customer_ID": customers,
            "Segment": rng.choice(
                ["Consumer", "Corporate", "Home Office"], rows, p=[0.52, 0.3, 0.18]
            ),
            "Country": "United States",
            "City": [c for _, c in place],
            "State": [s for s, _ in place],
            "Postal_Code": [f"{z:05d}" for z in rng.integers(1000, 99999, rows)],
            "Region": region,
            "Category": category,
            "Sub_Category": sub,
            "Sales": sales,
            "Quantity": rng.integers(1, 15, rows),
            "Discount": discount,
            "Profit": profit,
        }
    )
    OUT.parent.mkdir(exist_ok=True)
    frame.to_csv(OUT, index=False, lineterminator="\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(frame):,} rows")


if __name__ == "__main__":
    main()
