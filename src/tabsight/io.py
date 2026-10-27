"""Loading data safely. This is the only module that opens files.

Rules (see docs/SECURITY_CHECKLIST.md):

- Local files only. URLs are rejected, so tabsight never makes a network request.
- No pickle or other formats that can run code. Supported: CSV/TSV/TXT, Excel (.xlsx/.xlsm,
  with defusedxml), Parquet (pyarrow >= 15), JSON records.
- The source file is never modified.
"""

from __future__ import annotations

import codecs
import csv
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from tabsight.warnings import ProfileWarning, UnsafeInputError, safe_repr, warn

__all__ = ["as_frame", "load"]

_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]{1,15}:(//|[^\\/])")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_TEXT_SUFFIXES = {".csv", ".tsv", ".txt"}
_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
_DELIMITERS = ",;\t|"
_NA_VALUES = ["", "NA", "N/A", "n/a", "NaN", "nan", "NULL", "null", "None", "none", "#N/A", "-"]
_PLAIN_NUMBER_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d{1,3})?")
_LEADING_ZERO_RE = re.compile(r"[+-]?0\d")
_BOOL_TEXT = {"true": True, "false": False}
_CHUNK = 1 << 20


def load(
    source: Any,
    *,
    encoding: str | None = None,
    sheet: str | int | None = None,
) -> pd.DataFrame:
    """Load a local file (CSV, TSV, TXT, Excel, Parquet, JSON) into a DataFrame.

    Text files are read as text first, then columns that are plain numbers become
    numbers. Codes with leading zeros (``"02134"``) stay text. Dates are left as text
    for tabsight's date reader, which reports what it assumed.
    """
    path = _local_path(source)
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return _read_text(path, encoding)
    if suffix in _EXCEL_SUFFIXES:
        return _read_excel(path, sheet)
    if suffix == ".parquet":
        return _read_parquet(path)
    if suffix == ".json":
        return _read_json(path, encoding)
    if suffix == ".xls":
        raise UnsafeInputError("old .xls files are not supported; save the file as .xlsx")
    raise UnsafeInputError(
        f"unsupported file type {safe_repr(suffix)}; use CSV, TSV, TXT, XLSX, Parquet or JSON"
    )


def as_frame(data: Any) -> pd.DataFrame:
    """Turn supported inputs into a pandas DataFrame without copying a DataFrame input."""
    if isinstance(data, pd.DataFrame):
        return data
    module = type(data).__module__
    if module.startswith("polars") and hasattr(data, "to_pandas"):
        frame = data.to_pandas()
        if not isinstance(frame, pd.DataFrame):
            raise UnsafeInputError("polars to_pandas() did not return a DataFrame")
        return frame
    if isinstance(data, str | Path):
        return load(data)
    if isinstance(data, Mapping):
        return pd.DataFrame(dict(data))
    if (
        isinstance(data, Sequence)
        and not isinstance(data, str | bytes)
        and all(isinstance(row, Mapping) for row in data)
    ):
        return pd.DataFrame.from_records(list(data))
    raise UnsafeInputError(
        f"cannot use {type(data).__name__} as data; pass a pandas or polars DataFrame, "
        "a list of dicts, a dict of lists, or a local file path"
    )


def _local_path(source: Any) -> Path:
    if isinstance(source, Path):
        path = source
    elif isinstance(source, str):
        text = source.strip()
        if _URL_RE.match(text) and not _WINDOWS_DRIVE_RE.match(text):
            raise UnsafeInputError(
                "tabsight does not download data (it never uses the network). "
                "Download the file yourself and pass the local path."
            )
        path = Path(text)
    else:
        raise UnsafeInputError(f"expected a file path, got {type(source).__name__}")
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {safe_repr(str(path), 200)}")
    return path


def _detect_encoding(path: Path) -> tuple[str, bool]:
    """Return (encoding, guessed). UTF-8 → UTF-8 with BOM → Windows-1252 → Latin-1."""
    with path.open("rb") as f:
        head = f.read(4)
        if head.startswith(codecs.BOM_UTF8):
            return "utf-8-sig", False
        f.seek(0)
        decoder: codecs.IncrementalDecoder = codecs.getincrementaldecoder("utf-8")()
        try:
            while chunk := f.read(_CHUNK):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
            return "utf-8", False
        except UnicodeDecodeError:
            pass
        f.seek(0)
        decoder = codecs.getincrementaldecoder("cp1252")()
        try:
            while chunk := f.read(_CHUNK):
                decoder.decode(chunk)
            return "cp1252", True
        except UnicodeDecodeError:
            return "latin-1", True


def _sniff_delimiter(path: Path, encoding: str) -> str:
    if path.suffix.lower() == ".tsv":
        return "\t"
    with path.open("r", encoding=encoding, newline="") as f:
        sample = f.read(64 * 1024)
    try:
        return csv.Sniffer().sniff(sample, delimiters=_DELIMITERS).delimiter
    except csv.Error:
        return ","


def _read_text(path: Path, encoding: str | None) -> pd.DataFrame:
    if encoding is None:
        encoding, guessed = _detect_encoding(path)
        if guessed:
            warn(
                f"{path.name} is not UTF-8; read it as {encoding}. "
                "Pass encoding=... if characters look wrong.",
                ProfileWarning,
            )
    else:
        try:
            codecs.lookup(encoding)
        except LookupError:
            raise UnsafeInputError(f"unknown encoding {safe_repr(encoding)}") from None
    sep = _sniff_delimiter(path, encoding)
    frame = pd.read_csv(
        path,
        sep=sep,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
        na_values=_NA_VALUES,
        engine="c",
    )
    return _infer_plain_types(frame)


def _infer_plain_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn text columns that are plain numbers or true/false into proper types."""
    out = {}
    for name in frame.columns:
        col = frame[name]
        values = col.dropna().astype(str).str.strip()
        if values.empty:
            out[name] = col
            continue
        lowered = values.str.lower()
        if lowered.isin(list(_BOOL_TEXT)).all():
            out[name] = col.map(
                lambda v: _BOOL_TEXT.get(str(v).strip().lower()) if pd.notna(v) else pd.NA
            )
            out[name] = out[name].astype("boolean")
            continue
        is_number = values.str.fullmatch(_PLAIN_NUMBER_RE).all()
        keeps_zeros = values.str.match(_LEADING_ZERO_RE).any()
        if is_number and not keeps_zeros:
            numbers = pd.to_numeric(col, errors="coerce")
            whole = numbers.dropna()
            is_int = (
                bool((whole == whole.round()).all()) and not values.str.contains(r"[.eE]").any()
            )
            if is_int:
                out[name] = (
                    numbers.astype("Int64") if numbers.isna().any() else numbers.astype("int64")
                )
            else:
                out[name] = numbers.astype("float64")
        else:
            out[name] = col
    return pd.DataFrame(out, index=frame.index)


def _read_excel(path: Path, sheet: str | int | None) -> pd.DataFrame:
    try:
        import openpyxl
    except ImportError:
        raise ImportError("reading Excel needs: pip install 'tabsight[excel]'") from None
    if not getattr(openpyxl, "DEFUSEDXML", False):
        raise UnsafeInputError(
            "reading Excel safely needs defusedxml (protects against XML bombs): "
            "pip install 'tabsight[excel]'"
        )
    return pd.read_excel(path, sheet_name=0 if sheet is None else sheet, engine="openpyxl")


def _read_parquet(path: Path) -> pd.DataFrame:
    try:
        import pyarrow
    except ImportError:
        raise ImportError("reading Parquet needs: pip install 'tabsight[parquet]'") from None
    major = int(str(pyarrow.__version__).split(".")[0])
    if major < 15:
        raise UnsafeInputError(
            f"pyarrow {pyarrow.__version__} has a known code-execution flaw (CVE-2023-47248); "
            "upgrade to pyarrow 15 or newer"
        )
    return pd.read_parquet(path, engine="pyarrow")


def _read_json(path: Path, encoding: str | None) -> pd.DataFrame:
    text = path.read_text(encoding=encoding or "utf-8-sig")
    data = json.loads(text)
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return pd.DataFrame.from_records(data)
    if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
        return pd.DataFrame(data)
    raise UnsafeInputError("JSON must be a list of objects or an object of lists")
