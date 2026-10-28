import json
from pathlib import Path

import pandas as pd
import pytest

from tabsight.io import as_frame, load
from tabsight.warnings import ProfileWarning, UnsafeInputError


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/data.csv",
        "http://10.0.0.1/x.csv",
        "ftp://host/file.csv",
        "s3://bucket/key.parquet",
        "file:///etc/passwd",
        "data:text/csv,a,b",
        "  HTTPS://EXAMPLE.COM/a.csv",
    ],
)
def test_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeInputError, match="never uses the network"):
        load(url)


@pytest.mark.parametrize("share", [r"\\server\share\x.csv", "//server/share/x.csv"])
def test_network_shares_are_rejected(share: str) -> None:
    with pytest.raises(UnsafeInputError, match="network shares"):  # never touch the share
        load(share)


def test_missing_file_and_bad_types(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "nope.csv")
    with pytest.raises(UnsafeInputError, match="unsupported file type"):
        load(write(tmp_path, "x.pkl", b"\x80\x04"))
    with pytest.raises(UnsafeInputError, match=r"\.xlsx"):
        load(write(tmp_path, "x.xls", b"x"))
    with pytest.raises(UnsafeInputError):
        load(12345)


def test_windows_drive_path_is_not_a_url(tmp_path: Path) -> None:
    path = write(tmp_path, "d.csv", b"a,b\n1,2\n")
    assert load(str(path.resolve())).shape == (1, 2)


def test_csv_types_keep_leading_zeros_and_convert_plain_numbers(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "d.csv",
        b"Postal,Qty,Sales,Flag,Date,Mixed\n"
        b"02134,3,10.5,true,2017-01-05,a\n"
        b"10001,4,20,false,2017-02-05,1\n"
        b"94105,,7.25,TRUE,2017-03-05,2\n",
    )
    df = load(path)
    assert df["Postal"].tolist() == ["02134", "10001", "94105"]
    assert str(df["Qty"].dtype) == "Int64"
    assert df["Sales"].dtype == "float64"
    assert df["Flag"].tolist() == [True, False, True]
    assert df["Date"].tolist()[0] == "2017-01-05"
    assert df["Mixed"].tolist() == ["a", "1", "2"]


def test_encodings(tmp_path: Path) -> None:
    utf8 = write(tmp_path, "u.csv", "City\nCórdoba\n".encode())
    assert load(utf8)["City"][0] == "Córdoba"

    bom = write(tmp_path, "b.csv", "﻿City\nZürich\n".encode())
    df = load(bom)
    assert list(df.columns) == ["City"] and df["City"][0] == "Zürich"

    win = write(tmp_path, "w.csv", "City,Price\nMálaga,€5\n".encode("cp1252"))
    with pytest.warns(ProfileWarning, match="cp1252"):
        df = load(win)
    assert df["City"][0] == "Málaga" and df["Price"][0] == "€5"

    with pytest.raises(UnsafeInputError, match="unknown encoding"):
        load(utf8, encoding="no-such-codec")


def test_semicolon_and_tab_delimiters(tmp_path: Path) -> None:
    semi = write(tmp_path, "s.csv", b"a;b;c\n1;2;3\n4;5;6\n")
    assert list(load(semi).columns) == ["a", "b", "c"]
    tsv = write(tmp_path, "t.tsv", b"a\tb\n1\t2\n")
    assert list(load(tsv).columns) == ["a", "b"]


def test_placeholders_become_missing(tmp_path: Path) -> None:
    path = write(tmp_path, "n.csv", b"x,y\n1,N/A\n2,-\n3,ok\n")
    assert load(path)["y"].isna().sum() == 2


def test_json_records_and_columns(tmp_path: Path) -> None:
    rec = tmp_path / "r.json"
    rec.write_text(json.dumps([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]), encoding="utf-8")
    assert load(rec).shape == (2, 2)
    cols = tmp_path / "c.json"
    cols.write_text(json.dumps({"a": [1, 2, 3]}), encoding="utf-8")
    assert load(cols).shape == (3, 1)
    bad = tmp_path / "bad.json"
    bad.write_text("42", encoding="utf-8")
    with pytest.raises(UnsafeInputError):
        load(bad)


def test_excel_round_trip_uses_defusedxml(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    pytest.importorskip("defusedxml")
    import openpyxl

    assert openpyxl.DEFUSEDXML is True
    path = tmp_path / "x.xlsx"
    pd.DataFrame({"Region": ["West", "East"], "Sales": [1.5, 2.5]}).to_excel(path, index=False)
    df = load(path)
    assert df["Sales"].sum() == 4.0


def test_parquet_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    path = tmp_path / "x.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(path)
    assert load(path)["a"].sum() == 3


def test_as_frame_inputs() -> None:
    df = pd.DataFrame({"a": [1]})
    assert as_frame(df) is df
    assert as_frame([{"a": 1}, {"a": 2}]).shape == (2, 1)
    assert as_frame({"a": [1, 2, 3]}).shape == (3, 1)
    with pytest.raises(UnsafeInputError):
        as_frame(42)
    with pytest.raises(UnsafeInputError):
        as_frame(["not", "dicts"])


def test_excel_decompression_bombs_are_refused_before_unpacking(tmp_path: Path) -> None:
    import zipfile

    bomb = tmp_path / "bomb.xlsx"  # 49 KB on disk, 50 MB unpacked
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"0" * 50_000_000)
    with pytest.raises(UnsafeInputError, match="decompression bomb"):
        load(bomb)
    not_zip = tmp_path / "fake.xlsx"
    not_zip.write_text("Region,Sales\nWest,1\n", encoding="utf-8")
    with pytest.raises(UnsafeInputError, match="not a valid workbook"):
        load(not_zip)


def test_deeply_nested_json_is_refused(tmp_path: Path) -> None:
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    with pytest.raises(
        UnsafeInputError, match="nested too deeply|list of objects"
    ):  # newer Pythons parse it
        load(deep)
