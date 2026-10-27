# Quickstart

This page takes one file from raw CSV to numbers you can put in front of someone, in six short steps. It uses `examples/superstore_sample.csv`, a synthetic file shaped like the well-known Superstore sales data: 1,200 orders from 2014 to 2017. It ships with the repository, so you can run every line as written.

## 1. Load the file

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
print(orders.shape)
print(
    orders.loc[orders.Postal_Code.str.startswith("0"), ["Order_Date", "Postal_Code", "Sales"]].head(
        3
    )
)
```

```text title="Output"
(1200, 18)
    Order_Date Postal_Code   Sales
21  01/26/2014       02765  598.43
37  02/21/2014       03510  235.89
39  02/22/2014       04891  121.28
```

Two things happened that `pd.read_csv` would not do. The postal codes kept their leading zeros, because tabsight reads text files as text first and only converts columns that are plainly numbers. And the dates are still text: tabsight's date reader deals with them later and tells you what it assumed.

## 2. Ask what tabsight understood

```python
prof = ts.profile(orders)
print(prof["Discount"].role, prof["Discount"].unit, prof["Discount"].agg)
print(prof["Discount"].reasons)
```

```text title="Output"
measure percent mean
('name suggests a percentage', 'values stored as fractions (0.15 = 15%)', 'averaged, because totals of rates/prices/scores are meaningless')
```

Discount is a percentage, so its totals would be meaningless; tabsight will average it. `print(prof)` shows the same reasoning for every column, and [Profiling columns](../guide/profiling.md) explains how to change any of it.

## 3. Check the data before trusting it

```python
report = ts.check(orders)
print(report.score)
print([issue.code for issue in report.issues][:5])
```

```text title="Output"
97
['no_variation', 'outliers', 'outliers']
```

The sample file is clean, so the report only has small notes: `Country` has a single value, and a few unusually large orders stand out (they are flagged, never removed). On a real export you would see trimmed spaces, `West` versus `west`, placeholder values and so on. `ts.check` never changes anything; [cleaning](../guide/cleaning.md) is a separate, optional step.

## 4. Group and summarise

```python
by_region = ts.aggregate(orders, "Region", ["Sales", "Profit", "Discount"])
print(by_region.values)
```

```text title="Output"
    Region     Sales   Profit  Discount
0     East  87642.84  2454.65      0.17
1     West  79286.84  3987.07      0.15
2  Central  64667.90  1913.81      0.15
3    South  43661.26   480.89      0.17
```

Sales and profit were added up, discount was averaged, and the regions came back largest first. Now monthly sales, keeping the two biggest regions and folding the rest into one row:

```python
monthly = ts.aggregate(orders, ["Order_Date", "Region"], "Sales", freq="month", top=2)
print(monthly.values.head(6))
print(monthly.other)
```

```text title="Output"
  Order_Date     Region    Sales
0 2014-01-01       East  3641.28
1 2014-01-01       West  1136.98
2 2014-01-01  Other (2)  1547.94
3 2014-02-01       East  1553.95
4 2014-02-01       West   272.02
5 2014-02-01  Other (2)  1717.43
{'Region': ('Central', 'South')}
```

The "Other" row is computed from the raw orders, so its numbers are exact, and `monthly.other` records which regions it contains.

## 5. Add a calculated field

Profit margin is the classic trap: the average of each order's margin is not the margin of all orders. Write it as an aggregate formula and tabsight divides the totals:

```python
margin = ts.calc("Margin = SUM(Profit) / SUM(Sales)")
by_category = ts.aggregate(orders, "Category", ["Sales", margin]).values
by_category["Margin"] = by_category["Margin"].map(lambda m: ts.format_number(m, "percent"))
print(by_category)
```

```text title="Output"
          Category      Sales Margin
0       Technology  111105.78   3.7%
1  Office Supplies   85475.89   3.7%
2        Furniture   78677.17   1.9%
```

## 6. Format the result

```python
total = by_region.values["Sales"].sum()
print(ts.format_number(total, "currency", "compact"))
print(ts.format_number(total, "currency", locale="en_IE", currency="EUR"))
```

```text title="Output"
$275.3K
€275,259
```

That's the core loop. From here, [how tabsight thinks](concepts.md) explains the rules behind these defaults, and the [user guide](../guide/loading-data.md) goes deeper into each step.
