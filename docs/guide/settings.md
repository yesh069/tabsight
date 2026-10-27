# Settings

Most settings are things you'd otherwise repeat on every call: your locale, your currency, whether your dates are day-first. There are two ways to set them.

## For the whole program

Put this near the top of a script or notebook:

```python
import tabsight as ts

ts.set_defaults(locale="en_IE", currency="EUR")
print(ts.format_number(1234.5, "currency"))
```

```text title="Output"
€1,235
```

## For one block of code

Inside a web server, two requests can run at the same time for two different users. Changing global defaults there would let one user's settings leak into the other's report. Use a `with` block instead; it only affects the code inside it, in that thread or async task:

```python
with ts.config(locale="de_DE"):
    print(ts.format_number(1234.5, "currency", decimals=2))
print(ts.format_number(1234.5, "currency", decimals=2))
```

```text title="Output"
1.234,50 €
€1,234.50
```

Calling `ts.config(...)` without `with` does nothing, so tabsight warns you if you try. That's an easy mistake to make, and a silent no-op would be worse.

When the same setting is given in several places, the most specific wins: an argument to the call, then a `with ts.config` block, then `ts.set_defaults`, then the built-in default.

## Every setting

| Setting | Default | What it does |
|---------|---------|--------------|
| `locale` | `"en_US"` | Number and date formats ([list](../reference/locales.md)) |
| `currency` | `"USD"` | 3-letter currency code |
| `dayfirst` | `None` | Day/month order for ambiguous dates; `None` means infer, then month-first |
| `fiscal_start` | `1` | Month the fiscal year starts, e.g. `4` for April |
| `week_start` | `"monday"` | `"monday"`, `"sunday"` or `"saturday"` |
| `missing` | `"gap"` | Empty periods: `"gap"`, `"zero"` or `"connect"` |
| `tz` | `None` | Time zone name |
| `theme` | `"light"` | `"light"`, `"dark"` or `"print"` |
| `palette` | `"classic10"` | Colour palette |
| `top` | `10` | Default top N for charts |
| `strict` | `False` | Turn tabsight warnings into errors |
| `quiet` | `False` | Hide data warnings |
| `max_size_mb` | `5.0` | Warn when an HTML file would be bigger than this |
| `min_group_size` | `None` | Hide groups with fewer rows than this |
| `csv_safe` | `True` | Protect CSV downloads from spreadsheet formula injection |

Every value is checked when you set it. A typo gets a suggestion rather than being ignored:

```python
from tabsight.warnings import InvalidSpecError

try:
    ts.set_defaults(curency="EUR")
except InvalidSpecError as err:
    print(err)
```

```text title="Output"
unknown setting(s): 'curency' (did you mean 'currency'?)
```

## Strict mode

In a scheduled job you may want a warning to stop the run rather than scroll past in a log. `strict=True` turns every tabsight warning into a `TabsightError`:

```python
import pandas as pd

from tabsight.warnings import TabsightError

ambiguous = pd.DataFrame({"Date": ["01/02/2017", "03/04/2017"], "Sales": [1.0, 2.0]})
with ts.config(strict=True):
    try:
        ts.profile(ambiguous)
    except TabsightError as err:
        print(err)
```

```text title="Output"
ProfileWarning: 'Date': day/month order assumed month-first (no value above 12 settles it; pass dayfirst=)
```
