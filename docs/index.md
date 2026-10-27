# tabsight

**BI-quality charts, world maps and dashboards from a pandas DataFrame. Rule-based. No LLM. One offline HTML file.**

tabsight looks at your data the way a careful analyst would. It works out what every column is, picks the right charts, formats every number properly and builds a dashboard you can open in any browser, with no server and no internet connection.

> [!NOTE]
> **Status: early development.** Phases 0–2 of 10 are done: reading, profiling, checking, cleaning, formatting and exact aggregation all work today. Charts arrive in Phase 3, maps in Phase 5 and dashboards in Phase 8. See the [roadmap](project/roadmap.md).

## What works today

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")  # local files only, encoding detected
prof = ts.profile(df)  # role, unit and aggregation of every column, with reasons
report = ts.check(df)  # data-quality report; changes nothing
monthly = ts.aggregate(df, ["Order_Date", "Region"], "Sales", freq="month")
margin = ts.aggregate(df, "Category", ts.calc("Margin = SUM(Profit) / SUM(Sales)"))
ts.format_number(2297200.86, "currency", "compact")  # '$2.3M'
```

## Why tabsight

| | tabsight |
|---|---|
| **Suggests, you decide** | Every guess (role, unit, aggregation, date order) has a reason you can read and an option to override it. |
| **Never changes your data** | Every function works on a copy. Cleaning is optional and lists every change. |
| **Exact numbers** | Averages, ratios and medians are stored in a form that stays exact when dashboards are filtered. |
| **Formatted like a business tool** | `$2.3M`, `15.6%`, `1.234,50 €`, `₹12.3L`, `FY2018 Q1` in 14 locales. |
| **Offline and private** | No network calls, no telemetry. Output is a single HTML file. |
| **No LLM** | Same input, same output, every time. Every choice can be explained. |

## Where to go next

- [Install tabsight](getting-started/installation.md)
- [Quickstart: from CSV to numbers you can trust in 5 minutes](getting-started/quickstart.md)
- [How tabsight thinks](getting-started/concepts.md): the six rules behind every feature
- [User guide](guide/loading-data.md): every feature with examples
- [API reference](reference/api.md)
