# Quickstart

This walk-through uses `examples/superstore_sample.csv`, a **synthetic** dataset shaped like the well-known Superstore sales data (1,200 orders, 2014–2017). It ships with the repository, so every example runs as written.

## 1. Load the data

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
print(df.shape)
```

`ts.load` reads local files only (it never downloads anything), detects the text encoding, and keeps codes like zip `02134` as text so the leading zero is not lost.

## 2. See what tabsight understood

```python
prof = ts.profile(df)
print(prof)
```

```text
Column        Role       Unit       Agg     Why
Row_ID        id         none       countd  name says it is an ID/code; never summed
Order_Date    time       none       none    text that reads as dates; 100% parse as %m/%d/%Y
Sales         measure    currency   sum     name suggests money
Discount      measure    percent    mean    name suggests a percentage; values stored as fractions ...
...
Hierarchies:
  Category -> Sub_Category
```

Every guess comes with a reason. IDs are never summed; discounts are averaged, not added up.

## 3. Check data quality

```python
report = ts.check(df)
print(report.score)  # out of 100
print(report.show())
```

Nothing is changed. If you want help fixing problems, see [Cleaning](../guide/cleaning.md).

## 4. Aggregate

```python
by_region = ts.aggregate(df, "Region", ["Sales", "Profit", "Discount"])
print(by_region.values)
```

Sales and Profit are summed, Discount is averaged, and rows are sorted largest first.

Monthly sales per region, with the top 2 regions kept and the rest in an exact "Other" row:

```python
monthly = ts.aggregate(df, ["Order_Date", "Region"], "Sales", freq="month", top=2)
print(monthly.values.head())
print(monthly.other)  # which regions are inside "Other"
```

## 5. Calculated fields

```python
margin = ts.calc("Margin = SUM(Profit) / SUM(Sales)")
result = ts.aggregate(df, "Category", ["Sales", margin])
print(result.values)
```

## 6. Format numbers

```python
total = by_region.values["Sales"].sum()
print(ts.format_number(total, "currency", "compact"))  # $275.3K
print(ts.format_number(total, "currency", locale="de_DE", currency="EUR"))
```

## Next

- [How tabsight thinks](concepts.md)
- [The user guide](../guide/loading-data.md)
