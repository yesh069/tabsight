# Cleaning (optional)

Most people already have their own way of cleaning data, so tabsight never cleans unless you ask it to. When you do, `ts.clean` hands back a cleaned *copy* plus a report of every change. The original DataFrame is left alone.

Using the same messy file as on the [checking](checking.md) page:

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
messy = orders.copy()
messy.loc[::50, "Region"] = " west "
messy.loc[::70, "Segment"] = "N/A"
messy.loc[::90, "Segment"] = "consumer"

cleaned, report = ts.clean(messy)
print(report.show())
```

```text title="Output"
Clean report (mode='safe'). Quality score before cleaning: 77/100

Applied:
  - [Segment] placeholder values (N/A, -, null...) set to missing (16 values)
  - [Region] removed extra spaces at the start/end (24 values)
  - [Order_Date] convert text to dates (%m/%d/%Y, order proven by the data) (1,200 values)
  - [Ship_Date] convert text to dates (%m/%d/%Y, order proven by the data) (1,200 values)

Suggested (not applied; use report.apply(id) or mode='auto'):
  - s1: [Segment] merge 1 spelling variant(s) into the most common spelling ('consumer' -> 'Consumer')
  - s2: [Region] merge 1 spelling variant(s) into the most common spelling ('west' -> 'West')

Reported only:
  - [Profit] 79 unusually large or small values (flagged, not removed)
  - [Sales] 21 unusually large or small values (flagged, not removed)
```

Notice the split. Trimming spaces and turning `N/A` into a real missing value can't change what the data means, so the default `"safe"` mode just does them. Merging `west` into `West` *probably* doesn't change the meaning either, but that's your call, so it's only suggested.

## Three modes

- `mode="safe"` (the default) applies the harmless fixes and suggests the rest.
- `mode="auto"` applies the suggestions too. It's handy for a quick first look; don't use it for numbers you'll publish.
- `mode="off"` changes nothing and lists everything as a suggestion.

Two fixes are deliberately cautious even in safe mode. Text is converted to numbers only when *every* value converts, and text is converted to dates only when every value parses *and* the day/month order is proven by the data (or you passed `dayfirst=`). Dropping duplicate rows only happens with `dedupe=True`, because two identical orders are sometimes two real orders.

## Accepting, rejecting, undoing

```python
for s in report.suggestions:
    print(s.id, s.column, s.action, "|", s.detail)

merged = report.apply("Region")
print(sorted(merged["Region"].dropna().unique()))
```

```text title="Output"
s1 Segment merge_case | merge 1 spelling variant(s) into the most common spelling ('consumer' -> 'Consumer')
s2 Region merge_case | merge 1 spelling variant(s) into the most common spelling ('west' -> 'West')
['Central', 'East', 'South', 'West']
```

`report.apply` takes a suggestion id or a column name. `report.undo("Region")` puts a column back the way it was. Each call returns a fresh DataFrame, and `report.data` always holds the latest one.

## Cleaning next month's file the same way

Once you're happy with the decisions, save them and replay them on the next export:

```python
_, decided = ts.clean(messy, mode="auto")
saved = decided.to_json()

next_month, _ = ts.clean(messy.head(200), decisions=saved)
print(sorted(next_month["Region"].dropna().unique()))
```

```text title="Output"
['Central', 'East', 'South', 'West']
```

Saved decisions are validated when they're loaded. Unknown actions, unexpected keys, odd date formats and huge mappings are all rejected, and a step for a column that no longer exists is skipped with a warning.
