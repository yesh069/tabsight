# Aggregating

`ts.aggregate` groups data by dimensions and computes measures **exactly**: the same numbers you would get from pandas, stored in a form that stays exact when a dashboard viewer filters.

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
result = ts.aggregate(df, "Region", ["Sales", "Profit", "Discount"])
print(result.values)
```

`result` is an `Aggregation`:

| Attribute | Contents |
|-----------|----------|
| `values` | The dimension and output columns only |
| `frame` | Everything, including internal parts (columns starting with `__`) |
| `dims`, `measures`, `outputs` | What was grouped and computed |
| `other` | For top N: which values are inside "Other" |
| `categories` | For top N: how many values there were |
| `notes` | Everything tabsight assumed or did |
| `suppressed` | Groups hidden by `min_group_size` |

## Choosing measures

```python
result = ts.aggregate(
    df,
    "Category",
    [
        "Sales",  # default for the column (sum)
        {"column": "Sales", "agg": "median", "name": "Median sale"},
        {"column": "Discount", "agg": "wavg", "weight": "Sales", "name": "Weighted discount"},
        {"column": "Order_ID", "agg": "countd", "name": "Orders"},
        ts.Measure(None, "count", name="Rows"),
    ],
)
print(result.values)
```

| `agg` | Meaning |
|-------|---------|
| `sum` | Total (a group with no values is missing, not 0) |
| `mean` | Average of the values present |
| `median` | Middle value |
| `min`, `max` | Smallest, largest (numbers or dates) |
| `count` | Number of values present |
| `countd` | Number of distinct values |
| `wavg` | Weighted average; needs `weight=` |

Text columns can only be counted. Summing an ID column warns you.

## Several dimensions

```python
result = ts.aggregate(df, ["Region", "Segment"], "Sales")
print(result.values.head())
```

## Top N and "Other"

```python
result = ts.aggregate(df, "Sub_Category", "Sales", top=5)
print(result.values)
print(result.other)  # {'Sub_Category': (...the rest...)}
print(result.categories)  # {'Sub_Category': 13}
```

- The rest become one row called `Other (n)`, always sorted last.
- "Other" is computed exactly from the raw rows. An average for "Other" is the average of all those rows, not an average of averages.
- A single leftover value is never hidden inside "Other".
- Top N applies to the **first category dimension**, never to dates. With `["Order_Date", "Region"]` and `top=2`, the top 2 regions are kept across all months.
- Ranking uses the first measure you asked for (which can be a [calculated field](calculated-fields.md)).

## Sorting

| `sort=` | Order |
|---------|-------|
| not given | Dates in time order; ordered categories (months, sizes...) in their order; otherwise largest first |
| `"desc"` / `"asc"` | By the first measure |
| `"none"` | Natural order of the values (`Item 2` before `Item 10`) |
| `"by:<measure>"` | By another output column |
| a list | Your own order; anything not listed comes after |

## Mixed currencies are never added together

If a money column sits next to a currency-code column with several codes, tabsight adds the currency column to the grouping automatically and warns:

```python
import pandas as pd

sales = pd.DataFrame(
    {"Region": ["W", "W", "E"], "Sales": [10.0, 20.0, 5.0], "Currency": ["EUR", "USD", "EUR"]}
)
print(ts.aggregate(sales, "Region", "Sales").values)
```

## Hiding small groups (privacy)

For HR, health or survey data, a group with one person reveals that person's value. `min_group_size` hides values of groups with fewer rows:

```python
result = ts.aggregate(df, "City", "Profit", min_group_size=110)
print(result.suppressed, result.notes)
```

## Why the numbers stay exact

Internally every measure is stored as re-combinable *parts* (`ts.aggregate` uses the same functions):

```python
from tabsight.aggregate import build_parts, combine_parts

m = ts.Measure("Discount", "mean")
parts = build_parts(
    df, ["Region", "Segment"], [m]
)  # fine-grained parts, as a dashboard stores them
west_only = parts[parts["Region"] == "West"]  # a viewer filters to West
print(combine_parts(west_only, ["Segment"], [m])[["Segment", "Discount"]])
```

Those numbers equal `df[df.Region == "West"].groupby("Segment").Discount.mean()` exactly. A property-based test checks this for random data, random filters and all eight aggregations.
