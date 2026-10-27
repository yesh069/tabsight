# Table calculations

Some numbers only make sense relative to the rows around them: a running total, a share of the total, this month versus last month. In Tableau these are table calculations; in tabsight they're `ts.table_calc`. They run on an aggregated result, after grouping.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
by_region = ts.aggregate(orders, "Region", "Sales")
share = ts.table_calc(by_region, "pct_of_total").frame
share["Share"] = share["Sales (% of total, shown rows)"].map(
    lambda v: ts.format_number(v, "percent")
)
print(share[["Region", "Sales", "Share"]])
```

```text title="Output"
    Region     Sales  Share
0     East  87642.84  31.8%
1     West  79286.84  28.8%
2  Central  64667.90  23.5%
3    South  43661.26  15.9%
```

The new column is called `Sales (% of total, shown rows)`, and the name says what it was divided by: the rows shown. In a dashboard that means "of whatever is currently filtered", which is what people usually expect. If you need a share of a fixed total instead, such as last year's full revenue, pass `fixed_total=` and the name changes to say so.

## Running totals restart per group

```python
monthly = ts.aggregate(orders, ["Order_Date", "Region"], "Sales", freq="month")
running = ts.table_calc(monthly, "running_total")
west = running.frame[running.frame.Region == "West"]
print(west[["Order_Date", "Sales", "Sales (running total)"]].head(4))
print(running.notes[-1])
```

```text title="Output"
   Order_Date    Sales  Sales (running total)
3  2014-01-01  1136.98                1136.98
7  2014-02-01   272.02                1409.00
11 2014-03-01  1432.82                2841.82
15 2014-04-01  1726.29                4568.11
Sales (running total): computed along 'Order_Date', restarting for each Region
```

A calculation runs *along* one dimension (time, when there is one) and restarts for each value of the others. Here it runs along `Order_Date` and restarts for each region. Pick a different direction with `along=`.

## The full list

| `calc=` | Result |
|---------|--------|
| `running_total` | Cumulative sum |
| `pct_of_total` | Share of the total |
| `rank` | Rank, largest = 1. Ties share the best rank (1, 1, 3) |
| `difference` | Change from the previous row |
| `pct_difference` | Change from the previous row, as a fraction of it |
| `moving_avg:N` | Average of the last N rows, N from 2 to 365 |

```python
monthly_total = ts.aggregate(orders, "Order_Date", "Sales", freq="month")
smooth = ts.table_calc(monthly_total, "moving_avg:3")
print(smooth.frame[["Order_Date", "Sales", "Sales (moving avg 3)"]].head(4))
```

```text title="Output"
  Order_Date    Sales  Sales (moving avg 3)
0 2014-01-01  6326.20               6326.20
1 2014-02-01  3543.40               4934.80
2 2014-03-01  3039.72               4303.11
3 2014-04-01  6138.11               4240.41
```

One warning you might see: a running total or share of an *average* rarely means anything, so tabsight warns if you ask for one. Use a sum, or a weighted average if the measure is a rate.
