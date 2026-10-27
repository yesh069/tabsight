# Calculated fields

`ts.calc` creates a new field from a formula, like a Tableau calculated field:

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
margin = ts.calc("Margin = SUM(Profit) / SUM(Sales)")
print(margin.level, margin.fields)  # aggregate ('Profit', 'Sales')
print(ts.aggregate(df, "Category", ["Sales", margin]).values)
```

Write it as `Name = formula`, or pass the name separately: `ts.calc("SUM(Profit) / SUM(Sales)", name="Margin")`.

## Two levels

| Level | Example | Computed |
|-------|---------|----------|
| **Row-level** | `[Profit] / [Sales]` | For every row, then aggregated (summed) |
| **Aggregate** | `SUM([Profit]) / SUM([Sales])` | After grouping |

For ratios you almost always want the **aggregate** form: total profit ÷ total sales, not the sum of each row's ratio. Aggregate formulas stay exact when a dashboard is filtered, because each `SUM(...)` inside is stored as an exact measure.

You cannot mix the two in one formula (`SUM([Sales]) / [Profit]` is an error), and aggregates cannot be nested (`SUM(SUM(...))`).

Row-level formulas can also be computed directly:

```python
ratio = ts.calc("[Unit Margin] = [Profit] / [Sales]")
print(ratio.evaluate(df).head())
```

## The language

**Fields**: `Sales`, or `[Order Date]` in brackets when the name has spaces or symbols.

**Values**: numbers (`3`, `0.15`, `1e6`), text in single or double quotes (`'West'`; write `''` for a quote inside), `TRUE`, `FALSE`, `NULL`.

**Operators** (lowest to highest precedence):

| Operators | Meaning |
|-----------|---------|
| `OR` | either |
| `AND` | both |
| `NOT` | not |
| `=` `==` `<>` `!=` `<` `<=` `>` `>=` | comparison |
| `+` `-` | add, subtract (`+` joins text) |
| `*` `/` `%` | multiply, divide, remainder |
| `-x` | negative |

**Conditions**:

```python
size = ts.calc("""Size = IF [Sales] >= 500 THEN 'Large'
                         ELSEIF [Sales] >= 100 THEN 'Medium'
                         ELSE 'Small' END""")
print(size.evaluate(df).value_counts())
```

All functions are listed in the [formula function reference](../reference/formula-functions.md).

## Parameters

`$Name` is a parameter whose value you supply:

```python
over = ts.calc("Over = SUM(Sales) - $Target")
print(ts.aggregate(df, "Region", [over], params={"Target": 50_000}).values)
```

Parameter values must be numbers, text (up to 500 characters) or true/false.

> [!NOTE]
> In offline HTML dashboards (a later phase), parameters can only change values computed **after** grouping, like `SUM(Sales) - $Target` or a Top N. A parameter inside a **row-level** formula (`[Sales] > $Threshold`) needs every row to be recomputed, so it needs server mode. `CalcField.needs_server` tells you.

## Missing values and errors

- Division by zero, `LN(0)`, `SQRT(-1)` and numeric overflow give a **missing value**, never an error or infinity.
- `ZN(x)` turns missing into 0; `IFNULL(x, y)` uses `y` when `x` is missing.
- Wrong types (`[Product] * 2`) give a clear error.

## Safety

Formulas are read by tabsight's own parser. **Nothing is ever executed as Python**: there is no `eval`, no attribute access and no imports. Only the listed functions exist. Limits protect against hostile formulas: 2,000 characters, 1,000 parts, 50 levels of nesting and 500-character text values. All of this is covered by injection, fuzz and resource tests.

```python
from tabsight.formulas import CalcError

try:
    ts.calc("X = __import__('os').system('whoami')")
except CalcError as err:
    print("rejected:", err)
```
