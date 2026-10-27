"""Principle 1: no public function ever changes the user's DataFrame."""

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest

import tabsight as ts

from .conftest import assert_unchanged, superstore_like


def messy() -> pd.DataFrame:
    df = superstore_like(120)
    df.loc[::7, "Region"] = " west "
    df.loc[::11, "Segment"] = "N/A"
    df["Amount_Text"] = [f"${v:,.2f}" for v in df["Sales"]]
    df["Ratio"] = np.where(np.arange(len(df)) % 13 == 0, np.inf, df["Discount"])
    df.index = pd.Index(range(1000, 1000 + len(df)), name="row")
    return df


CALLS: dict[str, Callable[[pd.DataFrame], Any]] = {
    "profile": lambda d: ts.profile(d),
    "profile+overrides": lambda d: ts.profile(d, overrides={"Quantity": "dimension"}),
    "check": lambda d: ts.check(d, as_of="2016-01-01"),
    "clean off": lambda d: ts.clean(d, mode="off"),
    "clean safe": lambda d: ts.clean(d),
    "clean auto+dedupe": lambda d: ts.clean(d, mode="auto", dedupe=True, dayfirst=False),
    "clean apply/undo": lambda d: (lambda r: (r.apply(r.suggestions[0].id), r.undo("Region")))(
        ts.clean(d)[1]
    ),
    "aggregate": lambda d: ts.aggregate(
        d, ["Order_Date", "Region"], ["Sales", "Amount_Text", "Discount"], freq="month", top=2
    ),
    "aggregate+calcs": lambda d: ts.aggregate(
        d,
        "Category",
        [ts.calc("M = SUM(Profit) / SUM(Sales)"), ts.calc("D = [Sales] * 2")],
        min_group_size=3,
    ),
    "table_calc": lambda d: ts.table_calc(ts.aggregate(d, "Region", "Sales"), "pct_of_total"),
    "calc row": lambda d: ts.calc("R = [Profit] / [Sales]").evaluate(d),
}


@pytest.mark.parametrize("name", list(CALLS))
def test_public_functions_leave_input_unchanged(name: str) -> None:
    df = messy()
    before = df.copy(deep=True)
    with pytest.MonkeyPatch.context():
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            CALLS[name](df)
    assert_unchanged(before, df)
    assert df.index.equals(before.index) and df.index.name == "row"
