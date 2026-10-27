# Formatting numbers and dates

A chart can be correct and still look amateur if its numbers read `2297200.8574`. Most of what makes business charts look finished is formatting, so tabsight formats every number by what it means.

```python
import tabsight as ts

revenue = 2_297_200.8574
print(ts.format_number(revenue, "currency", "compact"))
print(ts.format_number(revenue, "currency", "full"))
print(ts.format_number(revenue, "currency", "raw"))
```

```text title="Output"
$2.3M
$2,297,201
2297200.8574
```

Those are the three styles. `compact` is for axes and KPI cards, where space is tight. `full` is for tooltips and tables, where people want the actual figure. `raw` is for exports, where the next program wants a plain number. You'll rarely pick one by hand: charts choose the right style for each place.

## Units

The unit comes from [profiling](profiling.md), so most of the time you never pass it. When you call `format_number` directly, you choose:

```python
print(ts.format_number(0.156, "percent"))
print(ts.format_number(0.032, "pp"))
print(ts.format_number(5009, "count"))
print(ts.format_number(4.2, "duration", duration_unit="hours"))
print(ts.format_number(-1234, "currency", negative="parens"))
print(ts.format_number(0.082, "percent", sign=True))
```

```text title="Output"
15.6%
+3.2 pp
5,009
4h 12m
($1,234)
+8.2%
```

`pp` is percentage points: the difference between two percentages, which is always shown with a sign. Percentages stored as whole numbers (`15.6` instead of `0.156`) need `percent_scale="whole"`; profiling detects this for you.

A few rules hold everywhere. Rounding is half-up, so `2.5` becomes `3` (Python's built-in rounding would give `2`). Compact numbers are promoted after rounding, so `999,950` is `$1M`, not `$1000K`. And a missing or infinite value formats as an empty string, never as `nan`.

## Other countries

Thousands separators, decimal marks, where the currency symbol goes and how big numbers are abbreviated all depend on the country:

```python
for locale, currency in [("en_IE", "EUR"), ("de_DE", "EUR"), ("fr_FR", "EUR"), ("en_IN", "INR")]:
    full = ts.format_number(1_234_567.5, "currency", locale=locale, currency=currency)
    short = ts.format_number(1_234_567.5, "currency", "compact", locale=locale, currency=currency)
    print(f"{locale}  {full:>16}  {short}")
```

```text title="Output"
en_IE        €1,234,568  €1.2M
de_DE       1.234.568 €  1,2 Mio. €
fr_FR       1 234 568 €  1,2 M €
en_IN        ₹12,34,568  ₹12.3L
```

The Indian format groups digits in twos above a thousand (12,34,568) and abbreviates in lakh and crore. The French one uses a narrow space as the thousands separator. All 14 locales are in the [locale reference](../reference/locales.md). Set yours once with `ts.set_defaults(locale="en_IE", currency="EUR")`; see [settings](settings.md).

## Your own pattern

For a format the units don't cover, pass a small Excel-style pattern:

```python
print(ts.format_number(1234.567, pattern="#,##0"))
print(ts.format_number(0.1234, pattern="0.0%"))
print(ts.format_number(12.5, pattern='0.0" kg"'))
print(ts.format_number(1234.5, pattern='"€"#,##0.00', locale="de_DE"))
```

```text title="Output"
1,235
12.3%
12.5 kg
€1.234,50
```

Only this simple subset is accepted. Patterns with sections (`;`), colours or `{...}` placeholders are rejected, so a pattern can't be used to inject anything.

## Dates

```python
import pandas as pd

when = pd.Timestamp("2017-01-05 13:45")
for grain in ["year", "quarter", "month", "week", "day", "minute"]:
    print(f"{grain:8} {ts.format_date(when, grain)}")
print(ts.format_date(when, "month", "compact"))
print(ts.format_date(when, "day", locale="en_IE"))
print(ts.format_date(when, "day", locale="de_DE"))
print(ts.format_date(pd.Timestamp("2017-04-10"), "quarter", fiscal_start=4))
```

```text title="Output"
year     2017
quarter  Q1 2017
month    Jan 2017
week     W01 2017
day      Jan 5, 2017
minute   Jan 5, 2017 13:45
Jan '17
5 Jan 2017
5 Jan. 2017
FY2018 Q1
```

Month names are translated for English, German, French, Spanish, Italian, Dutch and Portuguese.
