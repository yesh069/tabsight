from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import tabsight.settings as cfg

REGIONS = {
    "West": ["California", "Washington", "Oregon"],
    "East": ["New York", "Pennsylvania", "Ohio"],
    "Central": ["Texas", "Illinois", "Michigan"],
    "South": ["Florida", "Georgia", "Virginia"],
}
CATEGORIES = {
    "Furniture": ["Chairs", "Tables", "Bookcases"],
    "Office Supplies": ["Binders", "Paper", "Storage", "Art"],
    "Technology": ["Phones", "Copiers", "Accessories"],
}


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    cfg.reset_defaults()


def superstore_like(rows: int = 600, seed: int = 7) -> pd.DataFrame:
    """A small, deterministic Superstore-shaped dataset for tests."""
    rng = np.random.default_rng(seed)
    region = rng.choice(list(REGIONS), rows)
    state = [rng.choice(REGIONS[r]) for r in region]
    category = rng.choice(list(CATEGORIES), rows)
    sub = [rng.choice(CATEGORIES[c]) for c in category]
    days = rng.integers(0, 4 * 365, rows)
    order_date = pd.Timestamp("2014-01-01") + pd.to_timedelta(days, unit="D")
    ship_date = order_date + pd.to_timedelta(rng.integers(1, 7, rows), unit="D")
    sales = np.round(rng.gamma(2.0, 120.0, rows), 2)
    discount = rng.choice([0.0, 0.1, 0.2, 0.3], rows)
    profit = np.round(sales * rng.normal(0.12, 0.2, rows), 2)
    return pd.DataFrame(
        {
            "Row_ID": np.arange(1, rows + 1),
            "Order_ID": [f"CA-{2014 + d // 365}-{100000 + i}" for i, d in enumerate(days)],
            "Order_Date": order_date.strftime("%m/%d/%Y"),
            "Ship_Date": ship_date.strftime("%m/%d/%Y"),
            "Segment": rng.choice(["Consumer", "Corporate", "Home Office"], rows),
            "Postal_Code": [f"{z:05d}" for z in rng.integers(1000, 99999, rows)],
            "Region": region,
            "State": state,
            "Category": category,
            "Sub_Category": sub,
            "Sales": sales,
            "Quantity": rng.integers(1, 15, rows),
            "Discount": discount,
            "Profit": profit,
        }
    )


@pytest.fixture
def store() -> pd.DataFrame:
    return superstore_like()


def assert_unchanged(before: pd.DataFrame, after: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(before, after, check_exact=True)
    assert list(before.columns) == list(after.columns)
