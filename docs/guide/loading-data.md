# Loading data

Every tabsight function accepts:

- a **pandas DataFrame** (used as is, never modified)
- a **polars DataFrame** (converted with `to_pandas()`, needs `pyarrow`)
- a **list of dicts** (`[{"Region": "West", "Sales": 10}, ...]`)
- a **dict of lists** (`{"Region": ["West"], "Sales": [10]}`)
- a **local file path**, read with `ts.load`

## `ts.load`

```python
import tabsight as ts

df = ts.load("examples/superstore_sample.csv")
print(df.dtypes.head())
```

| File type | How it is read |
|-----------|----------------|
| `.csv`, `.txt` | Delimiter detected (`,` `;` tab `\|`) |
| `.tsv` | Tab-separated |
| `.xlsx`, `.xlsm` | First sheet, or `sheet="Name"` / `sheet=2`. Needs the `excel` extra. Macros never run. |
| `.parquet` | Needs the `parquet` extra (pyarrow 15 or newer) |
| `.json` | A list of records, or an object of column lists |

Not supported on purpose: old `.xls` (save as `.xlsx`), pickle files and other formats that can run code.

### What `ts.load` does for you

- **Encoding.** Tries UTF-8, then UTF-8 with a byte-order mark, then Windows-1252, and warns which one it used. Many CSV files from Excel are Windows-1252. Override with `encoding="latin-1"`.
- **Leading zeros.** Text files are read as text first. Columns that are plain numbers become numbers, but codes like `02134` stay text.
- **True/false.** `true`/`false` columns become booleans.
- **Missing values.** `""`, `NA`, `N/A`, `null`, `None`, `-`, `#N/A` and similar become missing.
- **Dates stay text.** tabsight's date reader handles them later and tells you what it assumed (see [Dates and periods](dates.md)).

## Safety rules

> [!IMPORTANT]
> tabsight **never downloads anything.** Passing a URL raises an error. Download the file yourself and pass the local path.

```python
from tabsight.warnings import UnsafeInputError

try:
    ts.load("https://example.com/data.csv")
except UnsafeInputError as err:
    print(err)
```

- Excel files are only read with `defusedxml` installed, which blocks malicious XML.
- Parquet files are only read with pyarrow 15 or newer.
- Your file is never written to.
