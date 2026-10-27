# Calculated fields

Sometimes the number you need isn't a column. Profit margin, days to ship and order size buckets are formulas. `ts.calc` lets you write them in a small formula language that will feel familiar if you've used Tableau or Excel.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
margin = ts.calc("Margin = SUM(Profit) / SUM(Sales)")
result = ts.aggregate(orders, "Segment", ["Sales", margin]).values
result["Margin"] = result["Margin"].map(lambda m: ts.format_number(m, "percent"))
print(result)
```

```text title="Output"
       Segment      Sales Margin
0     Consumer  148427.19   2.7%
1    Corporate   76696.93   2.5%
2  Home Office   50134.72   5.7%
```

## Row-level or aggregate?

This is the one idea to get right. A formula can work on each row, or on the totals after grouping:

- `[Profit] / [Sales]` is **row-level**. It's computed for every order, then the results are added up.
- `SUM([Profit]) / SUM([Sales])` is an **aggregate** formula. tabsight adds up profit, adds up sales, then divides.

For ratios, you almost always want the aggregate form. Here's why, on the same data:

```python
row_margin = ts.calc("[Row margin] = [Profit] / [Sales]")
print(
    "average of order margins:",
    ts.format_number(row_margin.evaluate(orders).mean(), "percent", decimals=2),
)
print(
    "margin of the business:  ",
    ts.format_number(orders.Profit.sum() / orders.Sales.sum(), "percent", decimals=2),
)
```

```text title="Output"
average of order margins: 3.34%
margin of the business:   3.21%
```

On this synthetic file the two are close. On real data, with refunds and lots of small orders, they can be far apart, because a $3 order with a 60% margin counts as much as a $3,000 order in the first number. The second number is the margin of the business. Aggregate formulas also stay exact when a dashboard is filtered, because each `SUM(...)` inside is stored as an exact measure.

tabsight won't let you mix the two in one formula (`SUM([Sales]) / [Profit]` is an error), and it won't nest aggregates (`SUM(SUM(...))`).

## Writing formulas

Refer to columns by name, or in square brackets when the name has spaces: `[Order Date]`. Text goes in quotes, and `+` joins text. Conditions use `IF … THEN … ELSEIF … ELSE … END`:

```python
size = ts.calc("""Size = IF [Sales] >= 500 THEN 'Large'
                         ELSEIF [Sales] >= 100 THEN 'Medium'
                         ELSE 'Small' END""")
print(size.evaluate(orders).value_counts())
```

```text title="Output"
Size
Medium    630
Small     424
Large     146
Name: count, dtype: int64
```

Dates have their own functions:

```python
ship_days = ts.calc("Days to ship = DATEDIFF('day', [Order_Date], [Ship_Date])")
print(ship_days.evaluate(orders).value_counts().sort_index())
```

```text title="Output"
Days to ship
0    182
1    166
2    154
3    197
4    146
5    187
6    168
Name: count, dtype: int64
```

Every available function is listed in the [formula function reference](../reference/formula-functions.md).

## Parameters

A `$Name` in a formula is a value you supply when you run it, such as a target:

```python
gap = ts.calc("Gap to target = SUM(Sales) - $Target")
print(ts.aggregate(orders, "Region", [gap], params={"Target": 70_000}).values)
```

```text title="Output"
    Region  Gap to target
0     East       17642.84
1     West        9286.84
2  Central       -5332.10
3    South      -26338.74
```

> [!NOTE]
> Once dashboards arrive, a parameter will work offline only when it changes things computed *after* grouping, like this target or a Top N. A parameter inside a row-level formula (`[Sales] > $Threshold`) means every row must be recomputed, which needs server mode. `CalcField.needs_server` tells you which kind you have.

## Errors are values, not crashes

Dividing by zero, `LN(0)` and `SQRT(-1)` give a missing value rather than an error or infinity, so one bad row doesn't sink the whole result. Wrong types, such as multiplying a product name by two, do give a clear error.

## Formulas can't run code

The formula language is parsed by tabsight itself. Nothing is ever handed to Python's `eval`, so a formula can only call the listed functions:

```python
from tabsight.formulas import CalcError

for attempt in ("X = __import__('os')", "X = [Sales].__class__", "X = eval('1+1')"):
    try:
        ts.calc(attempt)
    except CalcError as err:
        print(f"{attempt:24} -> {err}")
```

```text title="Output"
X = __import__('os')     -> unknown function '__import__'
X = [Sales].__class__    -> unexpected character '.' at position 9
X = eval('1+1')          -> unknown function 'eval'
```

There are also limits on length (2,000 characters), nesting (50 levels) and text values (500 characters), so a formula pasted from somewhere else can't hang your session.
