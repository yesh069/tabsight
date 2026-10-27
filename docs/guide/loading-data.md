# Loading data

You can pass tabsight a pandas DataFrame directly and skip this page. But if your data is still in a file, `ts.load` avoids a handful of problems that `pd.read_csv` leaves to you.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
zips = orders["Postal_Code"]
print(zips[zips.str.startswith("0")].head(3).tolist())
print(orders["Sales"].dtype, orders["Quantity"].dtype)
print(orders["Order_Date"].head(2).tolist())
```

```text title="Output"
['02765', '03510', '04891']
float64 int64
['01/04/2014', '01/04/2014']
```

The postal codes are text, not numbers, so the leading zeros survive. tabsight reads every column as text first and only converts the ones that are plainly numbers with no leading zeros. The dates are still text on purpose. The [date reader](dates.md) handles them, and it reports what it assumed about day/month order instead of guessing silently.

## Encodings

A lot of CSV files that come out of Excel aren't UTF-8. They're Windows-1252, and `pd.read_csv` either crashes on them or mangles every `é` and `€`. `ts.load` tries UTF-8, then UTF-8 with a byte-order mark, then Windows-1252, and warns you which one it used. If the characters still look wrong, pass `encoding=` yourself.

It also works out the delimiter. European exports often use `;` instead of `,`, and that's picked up without you saying so.

## Other formats

Excel (`.xlsx`, `.xlsm`), Parquet and JSON work too; pass `sheet=` to pick an Excel sheet. Excel needs the `excel` extra and Parquet the `parquet` extra (see [installation](../getting-started/installation.md)). Old `.xls` files aren't supported; save them as `.xlsx`.

Anything else that tabsight functions accept works without `ts.load`: a polars DataFrame, a list of dicts, or a dict of lists.

## What tabsight refuses to do

`ts.load` never downloads anything. Give it a URL and you get an error rather than a network request:

```python
from tabsight.warnings import UnsafeInputError

try:
    ts.load("https://example.com/sales.csv")
except UnsafeInputError as err:
    print(err)
```

```text title="Output"
tabsight does not download data (it never uses the network). Download the file yourself and pass the local path.
```

The same thinking applies elsewhere. Pickle files can run code when they're opened, so they're not supported. Excel files are only read when `defusedxml` is installed, because it blocks malicious XML. Parquet is only read with pyarrow 15 or newer, because older versions had a code-execution bug. And your file is only ever read, never written.
