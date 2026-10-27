# Warnings and errors

All live in `tabsight.warnings`.

## Warnings

tabsight warns rather than stops (rule 3). Every warning is a subclass of `TabsightWarning`, so the standard library can filter them:

| Warning | When |
|---------|------|
| `TabsightWarning` | Base class |
| `DataWarning` | Something in the data may mislead (mixed currencies, summing IDs, % of total of an average) |
| `ProfileWarning` | A guess was made (assumed date order, guessed file encoding) |
| `CleanWarning` | Something about cleaning (a saved step for a missing column) |
| `FormatWarning` | A formatting fallback (unknown locale) |

```python
import warnings

import tabsight as ts

warnings.simplefilter("ignore", ts.warnings.ProfileWarning)  # hide one kind
warnings.simplefilter("default", ts.warnings.TabsightWarning)  # back to normal
```

To turn every tabsight warning into an error, use strict mode: `ts.set_defaults(strict=True)` or `with ts.config(strict=True):`.

## Errors

| Error | When |
|-------|------|
| `TabsightError` | Base class (and strict-mode warnings) |
| `InvalidSpecError` | An argument, setting, spec, schema or saved decision failed validation (also a `ValueError`) |
| `UnsafeInputError` | Input refused for safety: a URL, an unsupported file type, Excel without defusedxml, old pyarrow (also a `ValueError`) |
| `CalcError` | A formula cannot be parsed or evaluated (in `tabsight.formulas`; a subclass of `InvalidSpecError`) |

Messages show untrusted values shortened and quoted, so data cannot flood or fake error messages.
