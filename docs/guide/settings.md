# Settings

Settings are resolved in this order:

1. arguments to a single call (`locale="de_DE"`)
2. a `with ts.config(...)` block
3. `ts.set_defaults(...)`
4. built-in defaults

## For a whole program

```python
import tabsight as ts

ts.set_defaults(locale="en_IE", currency="EUR")
print(ts.format_number(10, "currency"))  # €10.00
```

## For a block of code (safe in web servers)

```python
with ts.config(locale="de_DE", currency="EUR"):
    print(ts.format_number(1234.5, "currency", decimals=2))  # 1.234,50 €
print(ts.current().locale)  # back to the defaults outside the block
```

`ts.config` settings live in Python's `contextvars`, so concurrent web requests (threads or async tasks) never see each other's settings.

> [!WARNING]
> `ts.config(...)` only works in a `with` block. Called on its own it does nothing, and tabsight warns you. Use `ts.set_defaults(...)` to change settings for the whole program.

## All settings

| Setting | Default | Meaning |
|---------|---------|---------|
| `locale` | `"en_US"` | Number and date formats ([list](../reference/locales.md)) |
| `currency` | `"USD"` | 3-letter ISO currency code |
| `dayfirst` | `None` | Day/month order for ambiguous dates; `None` = infer, then month-first |
| `fiscal_start` | `1` | Month the fiscal year starts (`4` = April) |
| `week_start` | `"monday"` | `"monday"`, `"sunday"` or `"saturday"` |
| `missing` | `"gap"` | Missing periods: `"gap"`, `"zero"` or `"connect"` |
| `tz` | `None` | Time zone name |
| `theme` | `"light"` | `"light"`, `"dark"` or `"print"` |
| `palette` | `"classic10"` | Categorical palette |
| `top` | `10` | Default top N for charts (later phases) |
| `strict` | `False` | Turn tabsight warnings into errors |
| `quiet` | `False` | Hide data warnings |
| `max_size_mb` | `5.0` | HTML size warning limit (later phases) |
| `min_group_size` | `None` | Hide groups smaller than this (privacy) |
| `csv_safe` | `True` | Protect CSV downloads from spreadsheet formula injection (later phases) |

Every value is validated. Unknown names get a "did you mean" error:

```python
from tabsight.warnings import InvalidSpecError

try:
    ts.set_defaults(curency="EUR")
except InvalidSpecError as err:
    print(err)
ts.set_defaults(locale="en_US", currency="USD")
```

## Strict mode

In tests or pipelines you may prefer errors to warnings:

```python
with ts.config(strict=True):
    pass  # any tabsight warning inside this block raises tabsight.warnings.TabsightError
```
