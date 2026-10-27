# Formatting numbers and dates

Good formatting is most of what makes a chart look professional. tabsight formats every number by its **unit**, in three **styles**:

| Style | Used for | Example |
|-------|----------|---------|
| `compact` | Axes, KPI cards | `$2.3M` |
| `full` | Tooltips, tables | `$2,297,201` |
| `raw` | Exports | `2297200.86` |

```python
import tabsight as ts

value = 2297200.8574
print(ts.format_number(value, "currency", "compact"))  # $2.3M
print(ts.format_number(value, "currency", "full"))  # $2,297,201
print(ts.format_number(value, "number", "raw"))  # 2297200.8574
```

## Units

| `unit=` | Examples |
|---------|----------|
| `currency` | `$2.3M`, `$2,297,201`, `$35.50` (2 decimals below 1,000; none for JPY/KRW) |
| `percent` | `15.6%` (from `0.156`; pass `percent_scale="whole"` for `15.6`) |
| `pp` | `+3.2 pp` (percentage points, always signed) |
| `count` | `5,009` |
| `number` | `12.35`, `50K` compact |
| `duration` | `3.2 days`, `4h 12m`, `2m 5s` (`duration_unit="seconds"/"minutes"/"hours"/"days"`) |

```python
print(ts.format_number(0.156, "percent"))  # 15.6%
print(ts.format_number(0.032, "pp"))  # +3.2 pp
print(ts.format_number(4.2, "duration", duration_unit="hours"))  # 4h 12m
```

### Rounding and promotion

- Rounding is **half-up** on the shortest decimal form (2.5 → 3), which is what people expect, and the browser runtime will do exactly the same.
- Compact numbers are promoted after rounding: `999,950` is `$1M`, not `$1000K`.
- Missing, NaN and infinite values give an empty string, never `nan`.

## Options

```python
print(ts.format_number(-1234, "currency", negative="parens"))  # ($1,234)
print(ts.format_number(0.082, "percent", sign=True))  # +8.2%
print(ts.format_number(1234.5, "number", decimals=2))  # 1,234.50
```

## Locales and currencies

```python
print(ts.format_number(1234.5, "currency", locale="en_IE", currency="EUR", decimals=2))  # €1,234.50
print(
    ts.format_number(1234.5, "currency", locale="de_DE", currency="EUR", decimals=2)
)  # 1.234,50 €
print(ts.format_number(1_230_000, "currency", "compact", locale="en_IN", currency="INR"))  # ₹12.3L
print(ts.format_number(123456, "number", locale="en_IN"))  # 1,23,456
```

All locales and currency symbols are in the [locale reference](../reference/locales.md). Set them once for a whole program with `ts.set_defaults(locale="en_IE", currency="EUR")` (see [Settings](settings.md)).

## Custom patterns

A small, safe subset of Excel-style patterns:

| Pattern | Example output |
|---------|----------------|
| `#,##0` | `1,235` |
| `0.0%` | `12.3%` |
| `"€"#,##0.00` | `€1,234.50` |
| `0.0" kg"` | `12.5 kg` |

```python
print(ts.format_number(1234.5, pattern='"€"#,##0.00'))
```

Patterns are checked by a strict parser. Anything else (sections with `;`, colours, `{...}` placeholders) is rejected, so a pattern can never inject code.

## Dates

```python
import pandas as pd

ts_ = pd.Timestamp("2017-01-05 13:45")
print(ts.format_date(ts_, "year"))  # 2017
print(ts.format_date(ts_, "quarter"))  # Q1 2017
print(ts.format_date(ts_, "month"))  # Jan 2017
print(ts.format_date(ts_, "month", "compact"))  # Jan '17
print(ts.format_date(ts_, "day"))  # Jan 5, 2017
print(ts.format_date(ts_, "day", locale="en_IE"))  # 5 Jan 2017
print(ts.format_date(ts_, "week"))  # W01 2017
print(ts.format_date(pd.Timestamp("2017-04-10"), "quarter", fiscal_start=4))  # FY2018 Q1
```

Month names are translated for English, German, French, Spanish, Italian, Dutch and Portuguese.
