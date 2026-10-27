# Installation

tabsight needs **Python 3.11 or newer** (3.11, 3.12, 3.13 and 3.14 are tested) and pandas 2.2 or newer (pandas 2 and 3 are both supported).

> [!NOTE]
> tabsight is not on PyPI yet. Until the first release, install it from a clone of the repository.

## From the repository

```bash
git clone https://github.com/yesh069/tabsight.git
cd tabsight
python -m pip install -e .
```

## Optional extras

The core package only needs pandas. Extra file formats need extra packages:

| Extra | Installs | Needed for |
|-------|----------|------------|
| `excel` | `openpyxl`, `defusedxml` | Reading `.xlsx` / `.xlsm` files. `defusedxml` protects against malicious XML ("XML bombs"); tabsight refuses to read Excel without it. |
| `parquet` | `pyarrow` (15 or newer) | Reading `.parquet` files. Older pyarrow has a known code-execution flaw (CVE-2023-47248), so tabsight refuses it. |
| `polars` | `polars`, `pyarrow` | Passing polars DataFrames. |
| `png` | `playwright` | Saving charts as images (later phase). Playwright downloads its own browser the first time. |
| `dev` | test and lint tools | Working on tabsight itself. |

```bash
python -m pip install -e ".[excel,parquet]"
```

## Check it works

```python
import tabsight as ts

print(ts.__version__)
print(ts.ECHARTS_VERSION)  # the bundled, offline chart library
```
