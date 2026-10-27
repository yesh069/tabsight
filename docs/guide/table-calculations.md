# Table calculations

Table calculations run **after** aggregation, on the rows of a result, as in Tableau. `ts.table_calc` returns a new result with one extra column.

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
monthly = ts.aggregate(df, ["Order_Date", "Region"], "Sales", freq="month")
running = ts.table_calc(monthly, "running_total")
print(running.frame[["Order_Date", "Region", "Sales", "Sales (running total)"]].head())
print(running.notes[-1])
```

| `calc=` | Result |
|---------|--------|
| `running_total` | Cumulative sum |
| `pct_of_total` | Share of the total |
| `rank` | Rank, largest = 1; ties share the best rank (1, 1, 3) |
| `difference` | Change from the previous row |
| `pct_difference` | Change from the previous row as a fraction of it |
| `moving_avg:N` | Average of the last N rows (N from 2 to 365) |

## Along and restarting

A calculation runs **along** one dimension (time by default, otherwise the first dimension) and **restarts** for each combination of the others. Above, the running total runs along `Order_Date` and restarts for each `Region`. Choose with `along=`.

## % of total: shown rows or fixed

By default `pct_of_total` divides by the total of the rows given (the *filtered* total in a dashboard). Pass `fixed_total=` to divide by an overall total. The column name says which was used.

```python
by_region = ts.aggregate(df, "Region", "Sales")
share = ts.table_calc(by_region, "pct_of_total")
print(share.values.columns.tolist(), share.frame.iloc[:, -1].round(3).tolist())
fixed = ts.table_calc(by_region, "pct_of_total", fixed_total=1_000_000.0)
print(fixed.frame.columns[-1])
```

> [!WARNING]
> A running total or % of total of an **average** is rarely meaningful, so tabsight warns. Use a sum, or a weighted average.

Other options: `measure=` (which output to use; default the first) and `name=` (the new column's name).
