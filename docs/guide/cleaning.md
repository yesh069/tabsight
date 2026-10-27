# Cleaning (optional)

Most people clean data their own way, so **tabsight never cleans unless you ask**. `ts.clean` returns a cleaned **copy** and a report listing every change. Your DataFrame is never touched.

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
messy = df.assign(
    Segment=df["Segment"].where(df.index % 40 != 0, "consumer"),
    Region=df["Region"].where(df.index % 50 != 0, " West "),
)

clean_df, report = ts.clean(messy)
print(report.show())
```

## Modes

| Mode | What happens |
|------|--------------|
| `"off"` | Nothing changes; everything is listed as a suggestion |
| `"safe"` (default) | Only fixes that cannot change meaning are applied; the rest are suggestions |
| `"auto"` | Suggestions are applied too |

## What each fix does

| Fix | `safe` | `auto` |
|-----|--------|--------|
| Placeholders (`N/A`, `-`, `null`...) → missing | applied | applied |
| Trim extra spaces | applied | applied |
| Numbers stored as text → numbers | applied when every value converts and the decimal separator is `.` | applied |
| Text dates → dates | applied when every value converts **and** day/month order is proven (or you passed `dayfirst=`) | applied |
| Merge spellings that differ only in capitals (into the most common spelling) | suggested | applied |
| Excel serial numbers in a date column (`43831` → 2020-01-01) | suggested | applied |
| Drop exact duplicate rows | only with `dedupe=True` | only with `dedupe=True` |
| Possible typos, outliers, unreadable values | reported only | reported only |

## Applying, undoing and inspecting

```python
print([(s.id, s.column, s.action) for s in report.suggestions])

merged = report.apply("Segment")  # apply every suggestion for a column (or pass a suggestion id)
restored = report.undo("Region")  # put one column back as it was
print(report.applied)
```

Each call returns a new DataFrame; `report.data` always holds the current result.

## Reusing decisions on new data

```python
_, auto_report = ts.clean(messy, mode="auto", dayfirst=False)
saved = auto_report.to_json()

next_month = messy.head(100)
cleaned_again, _ = ts.clean(next_month, decisions=saved)
```

Saved decisions are validated strictly: unknown actions, unexpected keys, bad date formats and oversized mappings are rejected. Steps for columns that no longer exist are skipped with a warning.
