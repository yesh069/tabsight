import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tabsight.aggregate import (
    OTHER_FLAG,
    Measure,
    aggregate,
    bucket,
    build_parts,
    combine_parts,
)
from tabsight.warnings import DataWarning, InvalidSpecError

from .conftest import assert_unchanged

# ---------------------------------------------------------------- basics


def test_default_aggregations_follow_the_profile(store: pd.DataFrame) -> None:
    before = store.copy(deep=True)
    res = aggregate(store, "Region", ["Sales", "Discount", "Quantity"])
    assert_unchanged(before, store)
    expected = store.groupby("Region").agg(Sales=("Sales", "sum"), Discount=("Discount", "mean"))
    got = res.values.set_index("Region")
    pd.testing.assert_series_equal(got["Sales"].sort_index(), expected["Sales"], check_names=False)
    pd.testing.assert_series_equal(
        got["Discount"].sort_index(), expected["Discount"], check_names=False
    )
    assert [m.agg for m in res.measures] == ["sum", "mean", "sum"]
    # rankings sort by value, largest first
    assert got["Sales"].is_monotonic_decreasing


def test_no_dims_gives_one_row(store: pd.DataFrame) -> None:
    res = aggregate(store, None, ["Sales", Measure(None, "count")])
    assert len(res.frame) == 1
    assert res.values["Sales"].iloc[0] == pytest.approx(store["Sales"].sum())
    assert res.values["Rows"].iloc[0] == len(store)


def test_weighted_average_median_and_countd(store: pd.DataFrame) -> None:
    res = aggregate(
        store,
        "Region",
        [
            {"column": "Discount", "agg": "wavg", "weight": "Sales", "name": "Wavg"},
            {"column": "Sales", "agg": "median", "name": "Median"},
            {"column": "Order_ID", "agg": "countd", "name": "Orders"},
        ],
    ).values.set_index("Region")
    for region, g in store.groupby("Region"):
        assert res.loc[region, "Wavg"] == pytest.approx(
            (g.Discount * g.Sales).sum() / g.Sales.sum()
        )
        assert res.loc[region, "Median"] == pytest.approx(g.Sales.median())
        assert res.loc[region, "Orders"] == g.Order_ID.nunique()


def test_all_missing_group_is_missing_not_zero() -> None:
    df = pd.DataFrame({"g": ["a", "a", "b"], "v": [1.0, 2.0, np.nan]})
    res = aggregate(df, "g", [{"column": "v", "agg": "sum"}]).values.set_index("g")
    assert res.loc["a", "v"] == 3.0 and math.isnan(res.loc["b", "v"])


def test_missing_dimension_values_are_kept() -> None:
    df = pd.DataFrame({"g": ["a", None, "a"], "v": [1.0, 2.0, 3.0]})
    res = aggregate(df, "g", "v").values
    assert len(res) == 2 and res["v"].sum() == 6.0


def test_text_numbers_and_infinities() -> None:
    df = pd.DataFrame(
        {"g": ["a", "a", "b"], "Amount": ["$1,000.00", "$2.50", "($5.00)"], "x": [1.0, np.inf, 2.0]}
    )
    res = aggregate(df, "g", ["Amount", {"column": "x", "agg": "sum"}]).values.set_index("g")
    assert res.loc["a", "Amount"] == 1002.5 and res.loc["b", "Amount"] == -5.0
    assert res.loc["a", "x"] == 1.0  # infinity treated as missing


def test_errors_and_warnings(store: pd.DataFrame) -> None:
    with pytest.raises(InvalidSpecError, match="did you mean 'Region'"):
        aggregate(store, "region", "Sales")
    with pytest.raises(InvalidSpecError, match="is text"):
        aggregate(store, "Region", {"column": "Segment", "agg": "sum"})
    with pytest.raises(InvalidSpecError, match="needs weight"):
        Measure("Discount", "wavg")
    with pytest.raises(InvalidSpecError):
        aggregate(store, ["Region", "Region"], "Sales")
    with pytest.warns(DataWarning, match="ID"):
        aggregate(store, "Region", {"column": "Row_ID", "agg": "sum"})


def test_mixed_currencies_are_split_automatically() -> None:
    df = pd.DataFrame(
        {"Region": ["W", "W", "E"], "Sales": [10.0, 20.0, 5.0], "Currency": ["EUR", "USD", "EUR"]}
    )
    with pytest.warns(DataWarning, match="never added together"):
        res = aggregate(df, "Region", "Sales")
    assert "Currency" in res.dims and len(res.frame) == 3


# ---------------------------------------------------------------- dates


def test_buckets() -> None:
    d = pd.Series(
        pd.to_datetime(["2017-02-14", "2017-05-31", "2017-11-05 13:45", None], format="ISO8601")
    )
    assert bucket(d, "month").tolist()[:2] == [
        pd.Timestamp("2017-02-01"),
        pd.Timestamp("2017-05-01"),
    ]
    assert bucket(d, "quarter").tolist()[:3] == [
        pd.Timestamp("2017-01-01"), pd.Timestamp("2017-04-01"), pd.Timestamp("2017-10-01")]  # fmt: skip
    assert bucket(d, "year", fiscal_start=4).tolist()[:2] == [
        pd.Timestamp("2016-04-01"),
        pd.Timestamp("2017-04-01"),
    ]
    assert bucket(d, "quarter", fiscal_start=4).tolist()[:3] == [
        pd.Timestamp("2017-01-01"), pd.Timestamp("2017-04-01"), pd.Timestamp("2017-10-01")]  # fmt: skip
    assert bucket(d, "week").iloc[0] == pd.Timestamp("2017-02-13")  # Monday
    assert bucket(d, "week", week_start="sunday").iloc[0] == pd.Timestamp("2017-02-12")
    assert bucket(d, "hour").iloc[2] == pd.Timestamp("2017-11-05 13:00")
    assert pd.isna(bucket(d, "quarter").iloc[3])
    with pytest.raises(InvalidSpecError):
        bucket(d, "decade")


def test_monthly_series_with_gaps_and_text_dates() -> None:
    df = pd.DataFrame(
        {"Order_Date": ["01/15/2017", "01/20/2017", "03/02/2017"], "Sales": [10.0, 5.0, 7.0]}
    )
    gaps = aggregate(df, "Order_Date", "Sales", freq="month").values
    assert gaps["Order_Date"].tolist() == list(
        pd.to_datetime(["2017-01-01", "2017-02-01", "2017-03-01"])
    )
    assert gaps["Sales"].iloc[0] == 15.0 and math.isnan(gaps["Sales"].iloc[1])
    zero = aggregate(df, "Order_Date", "Sales", freq="month", missing="zero").values
    assert zero["Sales"].iloc[1] == 0
    connect = aggregate(df, "Order_Date", "Sales", freq="month", missing="connect").values
    assert len(connect) == 2


def test_integer_years_and_fiscal_years() -> None:
    df = pd.DataFrame({"Year": [2015, 2016, 2016], "Sales": [1.0, 2.0, 3.0]})
    res = aggregate(df, "Year", "Sales").values
    assert res["Sales"].tolist() == [1.0, 5.0]
    sales = pd.DataFrame({"d": pd.to_datetime(["2017-03-31", "2017-04-01"]), "v": [1.0, 2.0]})
    fy = aggregate(sales, "d", {"column": "v", "agg": "sum"}, freq="year", fiscal_start=4).values
    assert len(fy) == 2


# ---------------------------------------------------------------- top N and sorting


def test_top_n_other_is_exact_and_lists_members() -> None:
    df = pd.DataFrame(
        {"Item": list("ABCDEFG") * 2, "Price": [10, 9, 8, 7, 6, 5, 4, 20, 19, 18, 17, 16, 15, 14]}
    ).astype({"Price": "float64"})
    res = aggregate(df, "Item", {"column": "Price", "agg": "mean"}, top=3)
    vals = res.frame
    assert vals["Item"].tolist()[:3] == ["A", "B", "C"]
    other = vals[vals[OTHER_FLAG].fillna(False).astype(bool)]
    assert other["Item"].iloc[0] == "Other (4)"
    # exact: mean of the raw rows of D..G, not a mean of means
    assert other["Price"].iloc[0] == pytest.approx(df[df.Item.isin(list("DEFG"))].Price.mean())
    assert res.other["Item"] == ("D", "E", "F", "G")
    assert res.categories["Item"] == 7
    assert vals["Item"].iloc[-1] == "Other (4)"  # Other always last


def test_top_n_with_a_date_first_ranks_the_category_dimension() -> None:
    df = pd.DataFrame(
        {
            "Month": pd.to_datetime(["2017-01-05", "2017-02-05"] * 4),
            "Region": ["A", "A", "B", "B", "C", "C", "D", "D"],
            "Sales": [10.0, 10.0, 8.0, 8.0, 1.0, 1.0, 2.0, 2.0],
        }
    )
    res = aggregate(df, ["Month", "Region"], "Sales", freq="month", top=2)
    assert res.other == {"Region": ("C", "D")}
    assert set(res.frame["Region"]) == {"A", "B", "Other (2)"}
    assert res.frame["Month"].map(type).eq(pd.Timestamp).all()
    only_dates = aggregate(df, "Month", "Sales", freq="month", top=1)
    assert "top N ignored" in " ".join(only_dates.notes)


def test_top_n_never_hides_a_single_value() -> None:
    df = pd.DataFrame({"g": list("ABCD"), "v": [4.0, 3.0, 2.0, 1.0]})
    res = aggregate(df, "g", "v", top=3)
    assert res.other == {} and len(res.frame) == 4


def test_sort_options_and_ordered_dims() -> None:
    df = pd.DataFrame({"Size": ["L", "S", "M", "XL"], "v": [1.0, 4.0, 3.0, 2.0]})
    assert aggregate(df, "Size", "v").values["Size"].tolist() == ["S", "M", "L", "XL"]
    assert aggregate(df, "Size", "v", sort="desc").values["Size"].tolist() == ["S", "M", "XL", "L"]
    assert aggregate(df, "Size", "v", sort="asc").values["Size"].tolist() == ["L", "XL", "M", "S"]
    assert aggregate(df, "Size", "v", sort=["XL", "L"]).values["Size"].tolist()[:2] == ["XL", "L"]
    items = pd.DataFrame({"Item": ["Item 10", "Item 2", "Item 1"], "v": [1.0, 1.0, 1.0]})
    assert aggregate(items, "Item", "v", sort="none").values["Item"].tolist() == [
        "Item 1",
        "Item 2",
        "Item 10",
    ]


# ---------------------------------------------------------------- privacy


def test_min_group_size_hides_small_groups() -> None:
    df = pd.DataFrame({"Team": ["A"] * 6 + ["B"], "Salary": [50.0] * 6 + [99.0]})
    res = aggregate(df, "Team", "Salary", min_group_size=5)
    vals = res.values.set_index("Team")
    assert vals.loc["A", "Salary"] == 300.0 and math.isnan(vals.loc["B", "Salary"])
    assert res.suppressed == 1 and any("fewer than 5" in n for n in res.notes)


# ---------------------------------------------------------------- the key property


AGG_CHOICES = ["sum", "count", "mean", "min", "max", "wavg", "countd", "median"]


@st.composite
def frames(draw: st.DrawFn) -> pd.DataFrame:
    n = draw(st.integers(1, 60))
    a = draw(st.lists(st.sampled_from(["x", "y", "z", None]), min_size=n, max_size=n))
    b = draw(st.lists(st.sampled_from(["p", "q"]), min_size=n, max_size=n))
    floats = st.floats(-1e6, 1e6, allow_nan=False) | st.just(math.nan)
    v = draw(st.lists(floats, min_size=n, max_size=n))
    w = draw(st.lists(st.floats(0, 100, allow_nan=False), min_size=n, max_size=n))
    return pd.DataFrame({"a": a, "b": b, "v": v, "w": w})


def _direct(df: pd.DataFrame, dims: list[str], m: Measure) -> pd.Series:
    """Compute the measure straight from raw rows with plain pandas."""
    g = df.groupby(dims, dropna=False, sort=False)
    if m.agg == "sum":
        return g["v"].sum(min_count=1)
    if m.agg == "count":
        return g["v"].count()
    if m.agg == "mean":
        return g["v"].mean()
    if m.agg in ("min", "max"):
        return getattr(g["v"], m.agg)()
    if m.agg == "countd":
        return g["v"].nunique()
    if m.agg == "median":
        return g["v"].median()
    both = df["v"].notna() & df["w"].notna()
    num = (
        (df["v"] * df["w"])
        .where(both)
        .groupby([df[d] for d in dims], dropna=False)
        .sum(min_count=1)
    )
    den = df["w"].where(both).groupby([df[d] for d in dims], dropna=False).sum(min_count=1)
    return (num / den).where(den != 0)


@settings(max_examples=150, deadline=None)
@given(frames(), st.sampled_from(AGG_CHOICES), st.sets(st.sampled_from(["x", "y", "z"])))
def test_reaggregating_parts_after_a_filter_equals_raw(
    df: pd.DataFrame, agg: str, keep: set[str]
) -> None:
    """The promise behind cross-filtering: filter the stored parts, re-combine, and the
    numbers equal computing from the filtered raw rows."""
    m = Measure("v", agg, weight="w" if agg == "wavg" else None)
    fine = build_parts(df, ["a", "b"], [m])  # what the HTML stores
    mask_raw = df["a"].isin(keep)
    mask_parts = fine["a"].isin(keep)
    from_parts = combine_parts(fine[mask_parts], ["b"], [m]).set_index("b")["v"]
    raw = df[mask_raw]
    if raw.empty:
        assert from_parts.empty
        return
    expected = _direct(raw, ["b"], m)
    got = from_parts.reindex(expected.index).astype("float64")
    pd.testing.assert_series_equal(
        got.sort_index(),
        expected.astype("float64").sort_index(),
        check_names=False,
        rtol=1e-9,
        atol=1e-6,
    )


def test_large_input_is_reasonably_fast() -> None:
    import time

    rng = np.random.default_rng(1)
    n = 300_000
    df = pd.DataFrame(
        {"g": rng.choice(list("ABCDEFGHIJ"), n), "v": rng.random(n), "w": rng.random(n)}
    )
    start = time.perf_counter()
    aggregate(df, "g", ["v", {"column": "v", "agg": "wavg", "weight": "w", "name": "wv"}], top=5)
    assert time.perf_counter() - start < 5


def test_other_stays_inside_each_date_when_grouping_by_date_first() -> None:
    """Regression: 'Other' rows used to be pushed below every date."""
    df = pd.DataFrame(
        {
            "Month": pd.to_datetime(["2017-01-05", "2017-02-05"] * 3),
            "Region": ["A", "A", "B", "B", "C", "C"],
            "Sales": [10.0, 10.0, 5.0, 5.0, 1.0, 1.0],
        }
    )
    vals = aggregate(df, ["Month", "Region"], "Sales", freq="month", top=1).values
    assert vals["Month"].is_monotonic_increasing
    assert vals["Region"].tolist() == ["A", "Other (2)", "A", "Other (2)"]


def test_ordered_categorical_keeps_its_order() -> None:
    # pandas 2 crashed mapping a categorical to sort keys (tuples became a MultiIndex)
    df = pd.DataFrame(
        {
            "Priority": pd.Categorical(
                ["Low", "High", "Low", "Medium"], categories=["Low", "Medium", "High"], ordered=True
            ),
            "Sales": [1.0, 2.0, 3.0, 4.0],
        }
    )
    result = aggregate(df, "Priority", "Sales").values
    assert list(result["Priority"]) == ["Low", "Medium", "High"]
    assert list(result["Sales"]) == [4.0, 4.0, 2.0]
