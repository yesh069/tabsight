# Checking data quality

`ts.check` reads your data and tells you what looks wrong. It doesn't change anything, so it's safe to run on everything, every time.

To see it do some work, here's the sample file with a few typical export problems added: stray spaces, a lower-case region, and a placeholder instead of a missing value.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
messy = orders.copy()
messy.loc[::50, "Region"] = " west "
messy.loc[::70, "Segment"] = "N/A"

report = ts.check(messy)
print(report.show())
```

```text title="Output"
Data check: 1,200 rows, 18 columns. Quality score 82/100

Warnings:
  - [Region] 1 value(s) spelled with different capitals  e.g. 'West / west'
  - [Region] 24 values with extra spaces at the start or end  e.g. ' west '
  - [Segment] 18 placeholder values that mean 'missing'  e.g. 'N/A'

Infos:
  - [Country] every value is the same
  - [Profit] 79 unusually large or small values (flagged, not removed)  e.g. 572.27, 477.88, 472.04
  - [Sales] 21 unusually large or small values (flagged, not removed)  e.g. 2076.52, 2019.26, 1730.36
```

The score starts at 100 and drops 15 for each error, 5 for each warning and 1 for each note. Treat it as a quick summary for comparing files, and read the issues for the actual picture.

## Working with the report

Each issue has a severity, a code, a message and a few examples. Filter by column when you're fixing one thing at a time:

```python
for issue in report.for_column("Region"):
    print(issue.severity, issue.code, "|", issue.message, "|", issue.examples)
```

```text title="Output"
warning case_variants | 1 value(s) spelled with different capitals | ("'West / west'",)
warning untrimmed | 24 values with extra spaces at the start or end | ("' west '",)
```

`report.to_dict()` gives you plain data if you want to log it or fail a pipeline on it.

## What it looks for

| Code | What it means |
|------|---------------|
| `empty` | No rows or no columns |
| `all_missing` | A column where every value is missing |
| `missing` | Some values are missing |
| `no_variation` | Every value is the same |
| `infinite` | Infinite numbers (treated as missing) |
| `outliers` | Values far outside the usual range (beyond 3 × the interquartile range). Flagged, never removed |
| `negative_counts` | Negative values in a count (often returns) |
| `mixed_types` | Numbers and text mixed in one column |
| `placeholders` | `N/A`, `-`, `null`, `?` and similar, standing in for missing values |
| `untrimmed` | Extra spaces at the start or end |
| `case_variants` | The same value with different capitals, like `West` and `west` |
| `possible_typos` | A rare value very close to a common one (`Dubiln` / `Dublin`) |
| `numbers_as_text` | Numbers stored as text |
| `unparsed_dates`, `unparsed_numbers` | Values that couldn't be read |
| `suspicious_dates` | Dates before 1901, usually a placeholder |
| `future_dates` | Dates after `as_of` (only checked when you pass `as_of`) |
| `date_order` | Rows where, for example, the ship date is before the order date |
| `duplicate_rows` | Exact duplicates (kept) |
| `note` | Something tabsight did while reading, such as renaming a duplicate column |

## Why future dates need `as_of`

tabsight never reads your computer's clock. Otherwise a report run today and the same report run next week could disagree. If you want future dates flagged, tell it what "today" is:

```python
report = ts.check(orders, as_of="2016-06-30")
for issue in report.issues:
    if issue.code == "future_dates":
        print(issue.column, "|", issue.message)
```

```text title="Output"
Order_Date | 461 dates after 2016-06-30
Ship_Date | 463 dates after 2016-06-30
```
