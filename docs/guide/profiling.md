# Profiling columns

Before tabsight groups, sums or charts anything, it decides what each column is. `ts.profile` shows you those decisions and the reasoning behind each one.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
prof = ts.profile(orders)
print(prof["Sales"])
```

```text title="Output"
Sales: measure, currency, summed (name suggests money)
```

Each column's profile reads as one line: what it is, how it will be summarised, and why. The same information is on the object as `role`, `unit`, `agg` and `reasons`, and `print(prof)` shows every column as a table, as on the [home page](../index.md).

## How the guesses are made

tabsight reads the *data* first and the *name* second. A column is only treated as dates if at least 95% of its values actually read as dates; a column called `Date` full of product names stays text.

When it does look at names, it splits them into whole words. `OrderDate` becomes `order` + `date`. This is what keeps `Lifetime_Value` from being mistaken for a time column, a mistake substring matching makes all the time:

```python
import pandas as pd

customers = pd.DataFrame({"Lifetime_Value": [120.0, 480.5, 75.25, 990.0]})
print(ts.profile(customers)["Lifetime_Value"].role)
```

```text title="Output"
measure
```

Some rules worth knowing:

- A column is an **ID** if its name contains a word like `id`, `code`, `zip` or `sku`, or if every value is different. IDs are counted, never summed. Adding up postal codes is a classic bug.
- **Units** come from the name first (`Sales (€)`, `Price_USD`, `Duration_hrs`), then from symbols in the data (`$1,234.50`, `15%`), then from words like *sales*, *discount* or *quantity*.
- **Percentages and rates are averaged**, and so are prices, scores and ratings. Their totals are meaningless.
- **Months, weekdays, sizes, Likert answers** and *low/medium/high* keep their natural order instead of sorting alphabetically.
- Whole numbers between 1800 and 2200 in a column called *Year* are treated as years.

## Hierarchies

tabsight also notices when one column sits inside another: every sub-category belongs to exactly one category. Those pairs become drill-down paths later on.

```python
print(prof.hierarchies)
```

```text title="Output"
(('Category', 'Sub_Category'), ('Region', 'City'), ('Region', 'State'))
```

To avoid coincidences, it only looks at columns with fewer than 500 distinct values, skips IDs, and requires the parent to have fewer values than the child.

## When tabsight gets it wrong

Change any decision with `overrides=`. Pass a role name, or a dict with `role`, `unit`, `agg`, `currency`, `percent_scale`, `order`, `date_format` or `dayfirst`:

```python
prof = ts.profile(orders, overrides={"Quantity": "dimension", "Discount": {"agg": "wavg"}})
print(prof["Quantity"].role, prof["Quantity"].overridden)
```

```text title="Output"
dimension True
```

Misspell a column and you get a suggestion rather than a silent no-op:

```python
from tabsight.warnings import InvalidSpecError

try:
    ts.profile(orders, overrides={"sales": "measure"})
except InvalidSpecError as err:
    print(err)
```

```text title="Output"
column 'sales' not found; did you mean 'Sales'?
```

## Reusing decisions next month

If you've tuned the profile for a monthly export, save the decisions (not the data) and apply them to the next file:

```python
saved = prof.to_json()
next_month = ts.profile(orders, schema=saved)
print(next_month["Quantity"].role)
```

```text title="Output"
dimension
```

Saved schemas are checked strictly when loaded. Unknown keys, wrong types and oversized values are rejected, so it's safe to load one that a colleague sent you.

## Dates with an ambiguous day and month

`03/04/2017` is 4 March in the US and 3 April almost everywhere else. tabsight looks for proof in the data first: any value whose first number is above 12 means day-first. When there's no proof, it assumes month-first and warns you. If you know the answer, say so with `dayfirst=True`. [Dates and periods](dates.md) has the details.
