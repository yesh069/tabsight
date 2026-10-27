# Profiling columns

`ts.profile` works out what every column is: its **role**, **unit**, **default aggregation**, any natural **order**, and **hierarchies** between columns. Every decision has a reason, and every decision can be overridden.

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
prof = ts.profile(df)
print(prof.show())
```

## Looking at one column

```python
sales = prof["Sales"]
print(sales.role, sales.unit, sales.agg)  # measure currency sum
print(sales.reasons)
print(prof.names("measure"))  # ['Sales', 'Quantity', 'Discount', 'Profit']
print(prof.hierarchies)  # (('Category', 'Sub_Category'), ...)
```

## How decisions are made

**Names are split into whole words.** `OrderDate` becomes `order` and `date`; `Lifetime_Value` is *not* a time column, because `time` is not one of its words.

**Data is checked before the name.** A column is only a date if at least 95% of its values read as dates.

| Column looks like | Decision |
|-------------------|----------|
| Name word `id`, `code`, `key`, `zip`, `postal`, `sku` ... | `id`: counted, never summed |
| Every value different (20+ rows, whole numbers or text) | `id` |
| Whole numbers 1800–2200 named `year` / `fy` | `time` (year) |
| `lat`/`latitude` or `lon`/`lng`/`longitude` within range | `coord` |
| Small set of whole numbers named `rating`, `rank`, `level`, `priority` ... | ordered `dimension` |
| Text like `$1,234.50`, `15%`, `(500)`, `1.234,5 €` | `measure` (numbers stored as text) |
| Months, weekdays, sizes, Likert answers, Low/Medium/High | ordered `dimension` |
| 3-letter currency codes (`EUR`, `USD`) | `dimension`, marked as a currency column |
| Other text | `dimension` (or `text` when long free text) |

### Units

Units come from, in order:

1. **The column name**: `Sales (€)`, `Price_USD`, `Duration_hrs`, `Growth (%)`
2. **Symbols in the data**: `$`, `€`, `£`, `₹`, `%`
3. **Words in the name**: sales/revenue/profit/cost → currency; discount/rate/ratio/margin/share → percent; count/orders/quantity/units → count
4. Whole numbers → count; anything else → number

Percentages stored as `0.15` are recognised as fractions; values up to 100 as whole percents.

### Default aggregation

| Measure | Default |
|---------|---------|
| Money amounts, counts | `sum` |
| Percentages and rates | `mean` |
| Prices, unit costs, scores, ratings, ages, temperatures | `mean` |
| IDs used as measures | `countd` (distinct count) |

> [!TIP]
> A plain average of a rate is not always what you want. For example, discount weighted by sales is `agg="wavg", weight="Sales"`. See [Aggregating](aggregating.md).

### Hierarchies

If every value of one column belongs to exactly one value of another (every Sub_Category has one Category), they form a hierarchy. To avoid coincidences, only columns with fewer than 500 distinct values are checked, IDs are ignored, and the parent must have fewer values than the child.

## Overriding decisions

```python
prof = ts.profile(
    df,
    overrides={
        "Quantity": "dimension",  # just the role
        "Discount": {
            "agg": "wavg"
        },  # or any of: role, unit, agg, currency, percent_scale, order, date_format, dayfirst
    },
)
print(prof["Quantity"].role, prof["Quantity"].overridden)
```

Unknown column names get a "did you mean" error.

## Saving and reusing decisions

Save the decisions (not the data) and apply them to next month's file:

```python
saved = prof.to_json()
next_month = ts.profile(df, schema=saved)
print(next_month["Quantity"].role)
```

Saved schemas are validated strictly: unknown keys, wrong types and oversized values are rejected, so loading a schema someone else wrote is safe.

## Dates with ambiguous day/month order

`01/02/2017` could be 1 February or 2 January. tabsight looks for proof in the data (any first number above 12 means day-first). Without proof it assumes month-first and **warns**. Tell it explicitly:

```python
import pandas as pd

dates = pd.DataFrame({"Date": ["01/02/2017", "03/04/2017"]})
print(ts.profile(dates, dayfirst=True)["Date"].reasons)
```

## Other things the profiler handles

- A meaningful index (named, or dates) becomes a column; MultiIndex columns are flattened as `Sales / 2016`.
- Duplicate column names get ` (2)` added, with a note.
- Empty columns, constant columns and infinities are handled without errors.
- Mixed currencies: if a money column sits next to a currency-code column with several codes, tabsight warns and never adds them together (see [Aggregating](aggregating.md)).
