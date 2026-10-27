# Checking data quality

`ts.check` reports problems and gives a quality score out of 100. **It changes nothing.**

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
messy = df.assign(Region=df["Region"].where(df.index % 50 != 0, " west "))

report = ts.check(messy)
print(report.score)
print(report.show())
```

## What it looks for

| Code | Severity | Meaning |
|------|----------|---------|
| `empty` | error | No rows or no columns |
| `all_missing` | warning | Every value in a column is missing |
| `missing` | info | Some values are missing |
| `no_variation` | info | Every value is the same |
| `infinite` | warning | Infinite numbers (treated as missing) |
| `outliers` | info | Values far outside the usual range (3 × IQR). Flagged, never removed |
| `negative_counts` | info | Negative values in a count (returns?) |
| `mixed_types` | warning | Numbers and text mixed in one column |
| `placeholders` | warning | Values like `N/A`, `-`, `null`, `?` that mean "missing" |
| `untrimmed` | warning | Extra spaces at the start or end |
| `case_variants` | warning | `West` and `west` as different values |
| `possible_typos` | info | Rare values very close to common ones (`Dubiln` → `Dublin`?) |
| `numbers_as_text` | info | Numbers stored as text |
| `unparsed_dates` / `unparsed_numbers` | warning | Values that could not be read |
| `suspicious_dates` | warning | Dates before 1901 (often a placeholder) |
| `future_dates` | warning | Dates after `as_of` (only checked when you give `as_of`) |
| `date_order` | warning | e.g. ship date before order date |
| `duplicate_rows` | warning | Exact duplicate rows (kept) |
| `note` | info | Notes from reading (duplicate names renamed, index used...) |

## Using the report

```python
for issue in report.for_column("Region"):
    print(issue.severity, issue.code, issue.message, issue.examples)

data = report.to_dict()  # plain data, ready for JSON
```

## Future dates need `as_of`

tabsight never reads your computer's clock, so results never depend on when you run them. To check for future dates, say what "today" is:

```python
report = ts.check(df, as_of="2017-06-30")
print([i.code for i in report.issues if i.code == "future_dates"])
```

## Score

The score starts at 100 and loses 15 per error, 5 per warning and 1 per info item (minimum 0). It is a quick summary, not a verdict: read the issues.
