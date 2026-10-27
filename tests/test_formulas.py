import contextlib
import math
import time

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tabsight.aggregate import aggregate, build_parts, combine_parts
from tabsight.formulas import CalcError, calc

from .conftest import assert_unchanged


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Region": ["W", "W", "E", "E", "E"],
            "Sales": [100.0, 200.0, 50.0, 0.0, 150.0],
            "Profit": [10.0, -20.0, 5.0, 0.0, 30.0],
            "Order Date": pd.to_datetime(
                ["2017-01-05", "2017-02-10", "2017-03-15", "2017-04-20", "2018-05-25"]
            ),
            "Ship Date": pd.to_datetime(
                ["2017-01-08", "2017-02-11", "2017-03-20", "2017-04-21", "2018-05-26"]
            ),
            "Product": ["Phone X", "Chair", "Phone Y", "Desk", "Phone Z"],
        }
    )


# ---------------------------------------------------------------- parsing and row level


def test_definitions_and_levels() -> None:
    f = calc("Margin = SUM(Profit) / SUM(Sales)")
    assert (f.name, f.level, f.fields) == ("Margin", "aggregate", ("Profit", "Sales"))
    r = calc("[Unit Profit] = [Profit] / [Sales]")
    assert (r.name, r.level) == ("Unit Profit", "row")
    assert calc("Profit * 2", name="Double").name == "Double"


def test_row_level_evaluation(df: pd.DataFrame) -> None:
    before = df.copy(deep=True)
    ratio = calc("Ratio = [Profit] / [Sales]").evaluate(df)
    assert_unchanged(before, df)
    assert ratio.iloc[0] == 0.1 and math.isnan(ratio.iloc[3])  # 0/0 is missing, not an error
    days = calc("Days = DATEDIFF('day', [Order Date], [Ship Date])").evaluate(df)
    assert days.tolist() == [3, 1, 5, 1, 1]
    flag = calc(
        "Big = IF [Sales] >= 150 THEN 'big' ELSEIF [Sales] > 0 THEN 'small' ELSE 'none' END"
    ).evaluate(df)
    assert flag.tolist() == ["small", "big", "small", "none", "big"]
    phones = calc("P = CONTAINS([Product], 'Phone') AND NOT [Profit] < 0").evaluate(df)
    assert phones.tolist() == [True, False, True, False, True]
    assert calc("Y = YEAR([Order Date])").evaluate(df).tolist()[-1] == 2018
    assert calc("Z = ZN(NULL) + ROUND(2.567, 1)").evaluate(df).iloc[0] == pytest.approx(2.6)
    assert calc("M = MAX([Sales], 120)").evaluate(df).tolist() == [120, 200, 120, 120, 150]
    assert calc("Name = UPPER(LEFT([Product], 3)) + '!'").evaluate(df).iloc[0] == "PHO!"


def test_parameters(df: pd.DataFrame) -> None:
    f = calc("Hit = [Sales] > $Target")
    assert f.needs_server  # row-level + parameter: cannot recompute offline
    assert f.evaluate(df, {"Target": 120}).tolist() == [False, True, False, False, True]
    with pytest.raises(CalcError, match="missing parameter"):
        f.evaluate(df)
    agg = calc("Gap = SUM(Sales) - $Target")
    assert not agg.needs_server


# ---------------------------------------------------------------- aggregate level


def test_aggregate_formula_is_exact(df: pd.DataFrame) -> None:
    margin = calc("Margin = SUM(Profit) / SUM(Sales)")
    res = aggregate(df, "Region", ["Sales", margin])
    vals = res.values.set_index("Region")
    assert list(res.values.columns) == ["Region", "Sales", "Margin"]
    assert vals.loc["W", "Margin"] == pytest.approx(-10 / 300)
    assert vals.loc["E", "Margin"] == pytest.approx(35 / 200)


def test_aggregate_formula_survives_filtering_exactly(df: pd.DataFrame) -> None:
    margin = calc("Margin = SUM(Profit) / SUM(Sales)")
    res = aggregate(df, ["Region", "Product"], [margin])
    hidden = [m for m in res.measures if m.label.startswith("__")]
    parts = build_parts(
        pd.DataFrame(
            {
                "Region": df.Region,
                "Product": df.Product,
                "__calc0_0": df.Profit,
                "__calc0_1": df.Sales,
            }
        ),
        ["Region", "Product"],
        hidden,
    )
    keep = parts["Product"].str.contains("Phone")
    combined = combine_parts(parts[keep], ["Region"], hidden).set_index("Region")
    sums = df[df.Product.str.contains("Phone")].groupby("Region")[["Profit", "Sales"]].sum()
    exact = sums["Profit"] / sums["Sales"]
    got = combined["__calc0_0"] / combined["__calc0_1"]
    pd.testing.assert_series_equal(got.sort_index(), exact.sort_index(), check_names=False)


def test_row_level_calc_as_measure_and_top_by_calc(df: pd.DataFrame) -> None:
    double = calc("Double = [Sales] * 2")
    res = aggregate(df, "Region", [double])
    assert res.values.set_index("Region").loc["W", "Double"] == 600.0
    ratio = calc("Margin = SUM(Profit) / SUM(Sales)")
    ranked = aggregate(df, "Product", [ratio], top=2).values
    assert ranked["Product"].tolist()[:2] == ["Phone Z", "Phone X"]  # ranked by the formula


def test_min_group_size_hides_formula_values(df: pd.DataFrame) -> None:
    res = aggregate(df, "Region", [calc("Margin = SUM(Profit) / SUM(Sales)")], min_group_size=3)
    vals = res.values.set_index("Region")
    assert math.isnan(vals.loc["W", "Margin"]) and not math.isnan(vals.loc["E", "Margin"])


# ---------------------------------------------------------------- errors


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ("X = SUM(SUM(Sales))", "another aggregate"),
        ("X = SUM(Sales) / Profit", "cannot mix"),
        ("X = FOO(Sales)", "unknown function"),
        ("X = SUMM(Sales)", "did you mean SUM"),
        ("X = ROUND()", "takes 1-2"),
        ("X = (Sales", "expected ')'"),
        ("X = Sales +", "ends too early"),
        ("X = Sales ; DROP", "unexpected character"),
        ("X = IF Sales THEN 1", "expected 'END'"),
        ("SUM(Sales)", "Name = formula"),
    ],
)
def test_helpful_errors(formula: str, message: str) -> None:
    import re

    with pytest.raises(CalcError, match=re.escape(message)):
        calc(formula)


def test_field_and_type_errors(df: pd.DataFrame) -> None:
    with pytest.raises(CalcError, match=r"did you mean \[Sales\]"):
        calc("X = [Sale] * 2").evaluate(df)
    with pytest.raises(CalcError, match="needs numbers"):
        calc("X = [Product] * 2").evaluate(df)
    with pytest.raises(CalcError, match="aggregate formula"):
        calc("X = SUM(Sales)").evaluate(df)
    with pytest.raises(Exception, match="same name as a column"):
        aggregate(df, "Region", [calc("Sales = [Profit] * 2")])


# ---------------------------------------------------------------- security


@pytest.mark.parametrize(
    "attack",
    [
        "X = __import__('os').system('calc')",
        "X = [Sales].__class__",
        "X = Sales.__class__.__mro__",
        "X = eval('1+1')",
        "X = exec('x')",
        "X = open('secret.txt')",
        "X = getattr(Sales, 'x')",
        "X = lambda: 1",
        "X = `whoami`",
        "X = {0.__class__}",
        "X = Sales; import os",
        "X = Sales # comment",
        "X = 'abc' + \x00 'd'",
    ],
)
def test_code_injection_is_impossible(attack: str, df: pd.DataFrame) -> None:
    with pytest.raises(CalcError):
        calc(attack).evaluate(df)


def test_resource_limits() -> None:
    with pytest.raises(CalcError, match="longer than"):
        calc("X = " + "1+" * 1500 + "1")
    with pytest.raises(CalcError, match="nested more than"):
        calc("X = " + "(" * 60 + "1" + ")" * 60)
    with pytest.raises(CalcError, match="nested more than"):
        calc("X = " + "-" * 200 + "1")
    with pytest.raises(CalcError, match="more than 1000 parts"):
        calc("X = " + "+".join(["1"] * 600))
    with pytest.raises(CalcError, match="longer than 500"):
        calc("X = '" + "a" * 600 + "'")


def test_numeric_overflow_and_domain_errors_become_missing(df: pd.DataFrame) -> None:
    big = calc("X = POWER(10, 400) + EXP(1000) + LN(0) + SQRT(-1)").evaluate(df)
    assert big.isna().all()
    with pytest.raises(CalcError):
        calc("X = ROUND([Sales], 1000)").evaluate(df)
    with pytest.raises(CalcError):
        calc("X = LEFT([Product], 100000000)").evaluate(df)


def test_parameter_validation(df: pd.DataFrame) -> None:
    f = calc("X = [Sales] > $T")
    for bad in (
        {"T": object()},
        {"T": float("nan")},
        {"T": "x" * 600},
        {"bad name": 1},
        {"T": [1, 2]},
    ):
        with pytest.raises(CalcError):
            f.evaluate(df, bad)


def test_hostile_formulas_are_fast() -> None:
    start = time.perf_counter()
    for text in (
        "X = " + "[" * 5000,
        "X = " + "'" * 1999,
        "X = " + "a" * 1990,
        "X = " + "1e" * 990,
    ):
        with contextlib.suppress(CalcError):
            calc(text)
    assert time.perf_counter() - start < 2


@settings(max_examples=400, deadline=None)
@given(
    st.text(
        alphabet=st.sampled_from(list("SUMAVGIFTHENLs[]()+-*/<>=!,'\"$ 0123456789.ENDOR")),
        max_size=80,
    )
)
def test_parser_fuzz_only_raises_calc_errors(body: str) -> None:
    data = pd.DataFrame({"Sales": [1.0, 2.0], "s": [3.0, 4.0]})
    try:
        f = calc("X = " + body)
        if f.level == "row" and not f.params:
            f.evaluate(data)
    except CalcError:
        pass


@settings(max_examples=200, deadline=None)
@given(st.lists(st.floats(allow_nan=True, allow_infinity=True), min_size=1, max_size=20))
def test_arithmetic_never_crashes(values: list[float]) -> None:
    data = pd.DataFrame({"v": values})
    out = calc("X = ([v] * 2 - [v] / [v] + POWER([v], 3)) % 7 + ABS([v]) + LOG([v])").evaluate(data)
    assert len(out) == len(values)
    finite = out.dropna().astype("float64")
    assert np.isfinite(finite).all()
