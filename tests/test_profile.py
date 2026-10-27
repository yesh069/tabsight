import json

import numpy as np
import pandas as pd
import pytest

from tabsight.profile import profile, schema_from_dict, tokens
from tabsight.warnings import DataWarning, InvalidSpecError, ProfileWarning

from .conftest import assert_unchanged


def test_tokens_are_whole_words() -> None:
    assert tokens("OrderDate") == {"order", "date"}
    assert tokens("Lifetime_Value") == {"lifetime", "value"}
    assert "time" not in tokens("Lifetime_Value")
    assert tokens("Sub-Category") == {"sub", "category"}


def test_superstore_roles_units_and_aggs(store: pd.DataFrame) -> None:
    before = store.copy(deep=True)
    p = profile(store)
    assert_unchanged(before, store)

    roles = {f.name: f.role for f in p.fields}
    assert roles == {
        "Row_ID": "id",
        "Order_ID": "id",
        "Order_Date": "time",
        "Ship_Date": "time",
        "Segment": "dimension",
        "Postal_Code": "id",
        "Region": "dimension",
        "State": "dimension",
        "Category": "dimension",
        "Sub_Category": "dimension",
        "Sales": "measure",
        "Quantity": "measure",
        "Discount": "measure",
        "Profit": "measure",
    }
    assert p["Sales"].unit == "currency" and p["Sales"].agg == "sum"
    assert p["Profit"].unit == "currency"
    assert p["Quantity"].unit == "count" and p["Quantity"].agg == "sum"
    assert p["Discount"].unit == "percent" and p["Discount"].percent_scale == "fraction"
    assert p["Discount"].agg == "mean"
    assert p["Order_Date"].dayfirst is False and p["Order_Date"].grain == "day"
    assert ("Category", "Sub_Category") in p.hierarchies
    assert ("Region", "State") in p.hierarchies
    assert all(f.reasons for f in p.fields)


def test_lifetime_value_is_not_a_time_field() -> None:
    df = pd.DataFrame({"Lifetime_Value": np.linspace(10, 900, 30)})
    assert profile(df)["Lifetime_Value"].role == "measure"


def test_prices_and_rates_are_averaged() -> None:
    df = pd.DataFrame(
        {"Unit_Price": [9.99, 4.5, 3.2], "Conversion_Rate": [0.1, 0.2, 0.15], "Cost": [5, 6, 7]}
    )
    p = profile(df)
    assert p["Unit_Price"].agg == "mean"
    assert p["Conversion_Rate"].agg == "mean" and p["Conversion_Rate"].unit == "percent"
    assert p["Cost"].agg == "sum" and p["Cost"].unit == "currency"


def test_units_from_names_beat_words() -> None:
    df = pd.DataFrame({"Revenue (€)": [1.0, 2.0], "Wait_hrs": [1.5, 2.0], "Score (%)": [55, 80]})
    p = profile(df)
    assert (p["Revenue (€)"].unit, p["Revenue (€)"].currency) == ("currency", "EUR")
    assert (p["Wait_hrs"].unit, p["Wait_hrs"].duration_unit) == ("duration", "hours")
    assert p["Score (%)"].unit == "percent" and p["Score (%)"].percent_scale == "whole"


def test_numbers_stored_as_text_and_years_and_coords() -> None:
    df = pd.DataFrame(
        {
            "Amount": ["$1,200.00", "$35.50", "($20.00)"],
            "Year": [2015, 2016, 2017],
            "Latitude": [53.3, 51.5, 40.7],
            "Longitude": [-6.2, -0.1, -74.0],
        }
    )
    p = profile(df)
    assert p["Amount"].role == "measure" and p["Amount"].currency == "USD"
    assert p["Year"].role == "time" and p["Year"].grain == "year"
    assert (p["Latitude"].role, p["Latitude"].coord) == ("coord", "lat")
    assert p["Longitude"].coord == "lon"


def test_ordered_text_and_ranked_numbers() -> None:
    df = pd.DataFrame(
        {
            "Month": ["Mar", "Jan", "Feb", "Jan"],
            "Size": ["L", "S", "M", "XL"],
            "Rating": [3, 1, 5, 4],
            "Priority": ["High", "Low", "Medium", "Low"],
        }
    )
    p = profile(df)
    assert p["Month"].ordered == ("Jan", "Feb", "Mar")
    assert p["Size"].ordered == ("S", "M", "L", "XL")
    assert p["Rating"].role == "dimension" and p["Rating"].ordered == ("1", "3", "4", "5")
    assert p["Priority"].ordered == ("Low", "Medium", "High")


def test_ambiguous_dates_warn_and_respect_dayfirst() -> None:
    df = pd.DataFrame({"Date": ["01/02/2017", "03/04/2017"]})
    with pytest.warns(ProfileWarning, match="assumed month-first"):
        profile(df)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the user decided, so no warning
        p = profile(df, dayfirst=True)
    assert p["Date"].dayfirst is True
    assert "set by dayfirst" in " ".join(p["Date"].reasons)


def test_mixed_currencies_warn() -> None:
    df = pd.DataFrame({"Sales": [10.0, 20.0, 30.0], "Currency": ["EUR", "USD", "EUR"]})
    with pytest.warns(DataWarning, match="mixes 2 currencies"):
        p = profile(df)
    assert p["Currency"].currency_code_column


def test_false_hierarchies_are_avoided() -> None:
    df = pd.DataFrame(
        {
            "Customer_ID": [f"C{i}" for i in range(42)],
            "Region": ["West", "East"] * 21,
            "Flag": ["a", "b", "c"] * 14,  # crosses regions, so not a child of Region
        }
    )
    p = profile(df)
    assert all("Customer_ID" not in h for h in p.hierarchies)
    assert ("Region", "Flag") not in p.hierarchies


def test_index_multiindex_and_duplicate_columns() -> None:
    idx = pd.DatetimeIndex(pd.date_range("2020-01-01", periods=3, freq="D"), name="day")
    df = pd.DataFrame([[1, 2], [3, 4], [5, 6]], index=idx, columns=["x", "x"])
    before = df.copy()
    p = profile(df)
    assert p.names() == ["day", "x", "x (2)"]
    assert any("duplicate column" in n for n in p.notes)
    assert_unchanged(before, df)
    multi = pd.DataFrame(
        [[1, 2]], columns=pd.MultiIndex.from_tuples([("Sales", "2016"), ("Sales", "2017")])
    )
    assert profile(multi).names() == ["Sales / 2016", "Sales / 2017"]


def test_edge_cases() -> None:
    assert profile(pd.DataFrame()).fields == ()
    p = profile(pd.DataFrame({"empty": [None, None], "one": [5, 5], "inf": [np.inf, 1.0]}))
    assert p["empty"].source == "empty"
    assert p["one"].distinct == 1


def test_overrides_and_did_you_mean(store: pd.DataFrame) -> None:
    p = profile(store, overrides={"Quantity": "dimension", "Discount": {"agg": "wavg"}})
    assert p["Quantity"].role == "dimension" and p["Quantity"].overridden
    assert p["Discount"].agg == "wavg"
    with pytest.raises(InvalidSpecError, match="did you mean 'Sales'"):
        profile(store, overrides={"sales": "measure"})
    with pytest.raises(InvalidSpecError):
        profile(store, overrides={"Sales": {"role": "<script>"}})
    with pytest.raises(InvalidSpecError):
        profile(store, overrides={"Sales": {"evil": 1}})


def test_schema_round_trip_and_validation(store: pd.DataFrame) -> None:
    p = profile(store, overrides={"Quantity": "dimension"})
    saved = p.to_json()
    again = profile(store, schema=saved)
    assert again["Quantity"].role == "dimension"
    assert json.loads(saved)["tabsight_schema"] == 1
    for bad in (
        {"tabsight_schema": 99, "fields": {}},
        {"tabsight_schema": 1, "fields": [], "x": 1},
        {"tabsight_schema": 1, "fields": {"Sales": {"date_format": "%Y; DROP TABLE"}}},
        {"tabsight_schema": 1, "fields": {"Sales": {"order": ["a"] * 5000}}},
        "x" * 6_000_000,
    ):
        with pytest.raises((InvalidSpecError, json.JSONDecodeError)):
            schema_from_dict(bad)


def test_hostile_column_names_are_bounded_in_output() -> None:
    evil = "<img src=x onerror=alert(1)>\n" + "A" * 5000
    p = profile(pd.DataFrame({evil: [1, 2, 3]}))
    assert len(p.fields[0].name) <= 200
    assert "\n" in p.fields[0].name  # name kept as data; escaping happens at render time
    assert len(p.show().splitlines()[3]) < 400


def test_show_is_readable(store: pd.DataFrame) -> None:
    text = profile(store).show()
    assert "Hierarchies:" in text and "Category → Sub_Category" in text
