# Aggregating

`ts.aggregate` is a group-by that knows what your columns are. Give it the columns to group by and the measures you want, and it picks the right summary for each.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
result = ts.aggregate(orders, "Region", ["Sales", "Profit", "Discount"])
print(result.values)
```

```text title="Output"
    Region     Sales   Profit  Discount
0     East  87642.84  2454.65      0.17
1     West  79286.84  3987.07      0.15
2  Central  64667.90  1913.81      0.15
3    South  43661.26   480.89      0.17
```

Sales and profit are money, so they're summed. Discount is a percentage, so it's averaged. The regions come back largest first, because that's almost always what you want from a ranking. `result.values` is the table; `result.notes` records anything tabsight decided along the way.

## Choosing how to summarise

Name a column to get its default, or say exactly what you want:

```python
result = ts.aggregate(
    orders,
    "Category",
    [
        "Sales",
        {"column": "Sales", "agg": "median", "name": "Typical order"},
        {"column": "Discount", "agg": "wavg", "weight": "Sales", "name": "Discount (by sales)"},
        {"column": "Order_ID", "agg": "countd", "name": "Orders"},
    ],
)
print(result.values)
```

```text title="Output"
          Category      Sales  Typical order  Discount (by sales)  Orders
0       Technology  111105.78         402.58                 0.15     241
1  Office Supplies   85475.89          97.53                 0.15     725
2        Furniture   78677.17         285.35                 0.18     234
```

The options are `sum`, `mean`, `median`, `min`, `max`, `count`, `countd` (distinct) and `wavg` (weighted average, which needs `weight=`). Text columns can only be counted, and summing an ID column gets you a warning.

The weighted discount is worth a second look. A plain average treats a $5 order and a $5,000 order the same. Weighted by sales, the big orders count for more. That's usually the number a finance team means by "our average discount".

## Top N and "Other"

Charts with 13 bars are hard to read. `top=` keeps the biggest values and folds the rest into one row:

```python
result = ts.aggregate(orders, "Sub_Category", "Sales", top=5)
print(result.values)
print(result.other)
```

```text title="Output"
  Sub_Category      Sales
0      Copiers   31432.73
1  Accessories   28724.40
2     Machines   26986.87
3       Phones   23961.78
4    Bookcases   22669.28
5    Other (8)  141483.78
{'Sub_Category': ('Art', 'Binders', 'Chairs', 'Furnishings', 'Labels', 'Paper', 'Storage', 'Tables')}
```

The "Other" row is computed from the raw rows it contains, so if you asked for an average you get the true average of all those orders, not an average of averages. `result.other` lists exactly which values went in, which is what lets a dashboard filter correctly when someone clicks "Other". A single leftover value is never hidden: you'd just see it.

When you group by a date *and* a category, `top=` ranks the category across all dates. That's what a line chart with one line per region needs:

```python
monthly = ts.aggregate(orders, ["Order_Date", "Region"], "Sales", freq="month", top=2)
print(monthly.values.tail(4))
```

```text title="Output"
    Order_Date     Region    Sales
143 2017-12-01  Other (2)  2725.95
144 2018-01-01       East      NaN
145 2018-01-01       West   208.50
146 2018-01-01  Other (2)    78.45
```

## Sorting

The default depends on the column. Dates sort in time order, ordered categories (months, sizes, *low/medium/high*) keep their order, and everything else sorts largest first. Override it with `sort="asc"`, `sort="none"` (natural order, so `Item 2` comes before `Item 10`), `sort="by:Profit"` to sort by another output, or a list of values in the order you want.

## Different currencies are never added together

If a money column sits next to a column of currency codes, adding it up across currencies would be nonsense. tabsight splits by currency automatically and warns you:

```python
import pandas as pd

sales = pd.DataFrame(
    {
        "Region": ["West", "West", "East"],
        "Sales": [10.0, 20.0, 5.0],
        "Currency": ["EUR", "USD", "EUR"],
    }
)
print(ts.aggregate(sales, "Region", "Sales").values)
```

```text title="Output"
  Region Currency  Sales
0   West      EUR   10.0
1   West      USD   20.0
2   East      EUR    5.0
```

## Hiding small groups

For HR, health or survey data, a group with one person in it *is* that person. `min_group_size=` blanks out groups smaller than the number you give:

```python
result = ts.aggregate(orders, "City", "Profit", min_group_size=110)
print(result.values.head(4))
print(result.notes)
```

```text title="Output"
            City   Profit
0       Portland  2485.93
1        Seattle  2062.70
2       Columbus   993.08
3  New York City   729.88
('7 group(s) hidden: fewer than 110 rows',)
```

## Why the totals survive filtering

Under the hood, every measure is stored as parts that can be recombined exactly: a sum and a count for an average, the values themselves for a median. [How tabsight thinks](../getting-started/concepts.md#exact-numbers-even-after-filtering) shows this with real output. You'll rarely need it directly, but it's why dashboards built on tabsight can be filtered without the numbers drifting.
