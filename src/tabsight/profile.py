"""Working out what each column is: role, unit, aggregation, order and hierarchies.

``profile(df)`` never changes ``df``. Every guess records a reason (``Field.reasons``), and
every guess can be overridden (``overrides=``) or saved and reused (``Profile.to_dict``).
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from tabsight.io import as_frame
from tabsight.read import (
    DateReading,
    currency_code_for_symbol,
    read_dates,
    read_numbers,
    sample,
    unit_from_name,
)
from tabsight.settings import resolve
from tabsight.warnings import DataWarning, InvalidSpecError, ProfileWarning, safe_repr, warn

__all__ = ["AGGS", "ROLES", "UNITS", "Field", "Profile", "profile", "tokens"]

ROLES = ("dimension", "measure", "time", "id", "coord", "text")
UNITS = ("currency", "percent", "count", "number", "duration", "none")
AGGS = ("sum", "mean", "median", "min", "max", "count", "countd", "wavg", "none")
SCHEMA_VERSION = 1
MAX_HIERARCHY_COLUMNS = 30
MAX_HIERARCHY_DISTINCT = 500

_TIME_WORDS = {
    "date",
    "time",
    "datetime",
    "timestamp",
    "dt",
    "day",
    "month",
    "week",
    "quarter",
    "period",
}
_YEAR_WORDS = {"year", "yr", "fy", "yyyy"}
_ID_WORDS = {
    "id",
    "code",
    "key",
    "zip",
    "zipcode",
    "postal",
    "postcode",
    "uuid",
    "guid",
    "sku",
    "ean",
    "isbn",
    "phone",
}
_CURRENCY_WORDS = {
    "sales", "revenue", "revenues", "profit", "profits", "price", "cost", "costs", "amount", "income",
    "spend", "spending", "salary", "salaries", "budget", "fee", "fees", "payment", "payments", "tax",
    "gmv", "arr", "mrr", "earnings", "expense", "expenses", "wage", "wages", "pay", "balance", "turnover",
}  # fmt: skip
_PERCENT_WORDS = {
    "discount", "rate", "ratio", "pct", "percent", "percentage", "share", "margin", "growth", "churn",
    "conversion", "ctr", "utilization", "utilisation",
}  # fmt: skip
_COUNT_WORDS = {
    "count", "orders", "quantity", "qty", "units", "customers", "visits", "clicks", "views", "sessions",
    "users", "number", "num", "items", "transactions", "employees", "headcount", "population",
}  # fmt: skip
_MEAN_WORDS = {
    "price", "avg", "average", "mean", "median", "rate", "ratio", "pct", "percent", "percentage",
    "score", "rating", "temperature", "temp", "age", "unit", "per", "index",
}  # fmt: skip
_ORDINAL_INT_WORDS = {
    "rating",
    "stars",
    "rank",
    "level",
    "grade",
    "tier",
    "priority",
    "class",
    "month",
    "quarter",
    "weekday",
}
_LAT_WORDS = {"lat", "latitude"}
_LON_WORDS = {"lon", "lng", "long", "longitude"}

_ISO_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "CNY", "AUD", "CAD", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK",
    "HUF", "RON", "BGN", "TRY", "RUB", "BRL", "MXN", "ARS", "CLP", "COP", "PEN", "ZAR", "NGN", "KES",
    "EGP", "SAR", "AED", "ILS", "KRW", "SGD", "HKD", "TWD", "THB", "MYR", "IDR", "PHP", "VND", "NZD",
    "PKR", "BDT", "LKR",
}  # fmt: skip

_ORDERS: tuple[tuple[str, ...], ...] = (
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
    ("january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"),
    ("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
    ("q1", "q2", "q3", "q4"),
    ("xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl"),
    ("small", "medium", "large", "extra large"),
    ("very low", "low", "medium", "high", "very high", "critical"),
    ("none", "low", "medium", "high"),
    ("strongly disagree", "disagree", "neutral", "agree", "strongly agree"),
    ("strongly disagree", "disagree", "neither agree nor disagree", "agree", "strongly agree"),
    ("very dissatisfied", "dissatisfied", "neutral", "satisfied", "very satisfied"),
    ("never", "rarely", "sometimes", "often", "always"),
    ("poor", "fair", "good", "very good", "excellent"),
    ("bronze", "silver", "gold", "platinum"),
)  # fmt: skip

_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_SPLIT_RE = re.compile(r"[^0-9a-zA-Z]+")


def tokens(name: str) -> set[str]:
    """Whole-word tokens of a column name: ``"OrderDate"`` → {"order", "date"}."""
    spaced = _CAMEL_RE.sub(r"\1 \2", name[:200])
    return {t.lower() for t in _SPLIT_RE.split(spaced) if t}


@dataclasses.dataclass(frozen=True)
class Field:
    name: str
    role: str
    unit: str = "none"
    agg: str = "none"
    currency: str | None = None
    percent_scale: str | None = None  # "fraction" (0.15) or "whole" (15)
    duration_unit: str | None = None
    ordered: tuple[str, ...] | None = None
    grain: str | None = None
    date_format: str | None = None
    dayfirst: bool | None = None
    coord: str | None = None
    currency_code_column: bool = False
    distinct: int = 0
    missing: int = 0
    dtype: str = ""
    source: str = ""
    reasons: tuple[str, ...] = ()
    overridden: bool = False

    @property
    def is_measure(self) -> bool:
        return self.role == "measure"


@dataclasses.dataclass(frozen=True)
class Profile:
    fields: tuple[Field, ...]
    rows: int
    hierarchies: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()

    def __getitem__(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(_unknown_column(name, [f.name for f in self.fields]))

    def __contains__(self, name: object) -> bool:
        return any(f.name == name for f in self.fields)

    def names(self, role: str | None = None) -> list[str]:
        return [f.name for f in self.fields if role is None or f.role == role]

    def show(self) -> str:
        """A readable table of every guess and why it was made."""
        lines = [f"Profile: {self.rows:,} rows, {len(self.fields)} columns", ""]
        width = max((len(f.name) for f in self.fields), default=4)
        width = min(max(width, 6), 32)
        lines.append(f"{'Column':<{width}}  {'Role':<9}  {'Unit':<9}  {'Agg':<6}  Why")
        for f in self.fields:
            name = f.name if len(f.name) <= width else f.name[: width - 1] + "…"
            why = "; ".join(f.reasons)
            lines.append(f"{name:<{width}}  {f.role:<9}  {f.unit:<9}  {f.agg:<6}  {why}")
        if self.hierarchies:
            lines += ["", "Hierarchies:"] + ["  " + " -> ".join(h) for h in self.hierarchies]
        if self.notes:
            lines += ["", "Notes:"] + ["  " + n for n in self.notes]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.show()

    def to_dict(self) -> dict[str, Any]:
        """Save the decisions (not the data) so the same reading applies to new data."""
        fields: dict[str, Any] = {}
        for f in self.fields:
            entry: dict[str, Any] = {"role": f.role, "unit": f.unit, "agg": f.agg}
            for key in ("currency", "percent_scale", "date_format", "dayfirst"):
                if getattr(f, key) is not None:
                    entry[key] = getattr(f, key)
            if f.ordered is not None:
                entry["order"] = list(f.ordered)
            fields[f.name] = entry
        return {
            "tabsight_schema": SCHEMA_VERSION,
            "fields": fields,
            "hierarchies": [list(h) for h in self.hierarchies],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- overrides and schemas

_OVERRIDE_KEYS = {
    "role",
    "unit",
    "agg",
    "currency",
    "percent_scale",
    "order",
    "date_format",
    "dayfirst",
}
_MAX_NAME = 200
_MAX_ORDER = 1000
_DATE_FORMAT_RE = re.compile(r"(%[YymdbBHMSfjUWaAp]|[ ./:,T-])+")


def _unknown_column(name: object, names: Iterable[str]) -> str:
    names = list(names)
    hint = difflib.get_close_matches(str(name)[:_MAX_NAME], names, n=1)
    extra = f"; did you mean {hint[0]!r}?" if hint else ""
    return f"column {safe_repr(name)} not found{extra}"


def _validate_override(column: str, spec: Any) -> dict[str, Any]:
    if isinstance(spec, str):
        spec = {"role": spec}
    if not isinstance(spec, Mapping):
        raise InvalidSpecError(f"override for {safe_repr(column)} must be a role name or a dict")
    unknown = set(spec) - _OVERRIDE_KEYS
    if unknown:
        raise InvalidSpecError(f"unknown override key(s) {sorted(map(safe_repr, unknown))}")
    out: dict[str, Any] = {}
    for key, value in spec.items():
        allowed = {
            "role": ROLES,
            "unit": UNITS,
            "agg": AGGS,
            "percent_scale": ("fraction", "whole"),
        }
        if key in allowed:
            if value not in allowed[key]:
                raise InvalidSpecError(f"{key}={safe_repr(value)} is not one of {allowed[key]}")
        elif key == "currency":
            if not (isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value)):
                raise InvalidSpecError(f"currency={safe_repr(value)} must be a 3-letter code")
        elif key == "order":
            if (
                not isinstance(value, list | tuple)
                or len(value) > _MAX_ORDER
                or not all(isinstance(v, str) and len(v) <= _MAX_NAME for v in value)
            ):
                raise InvalidSpecError("order must be a list of up to 1000 short strings")
            value = tuple(value)
        elif key == "date_format":
            if not (
                isinstance(value, str) and len(value) <= 40 and _DATE_FORMAT_RE.fullmatch(value)
            ):
                raise InvalidSpecError(
                    f"date_format={safe_repr(value)} is not a simple strptime format"
                )
        elif key == "dayfirst" and value not in (True, False, None):
            raise InvalidSpecError("dayfirst must be True, False or None")
        out[key] = value
    return out


def schema_from_dict(data: Any) -> dict[str, dict[str, Any]]:
    """Validate a saved schema (``Profile.to_dict()``) and return it as overrides."""
    if isinstance(data, str):
        if len(data) > 5_000_000:
            raise InvalidSpecError("schema text is too large")
        data = json.loads(data)
    if not isinstance(data, Mapping) or data.get("tabsight_schema") != SCHEMA_VERSION:
        raise InvalidSpecError(f"not a tabsight schema (version {SCHEMA_VERSION} expected)")
    unknown = set(data) - {"tabsight_schema", "fields", "hierarchies"}
    if unknown:
        raise InvalidSpecError(f"unknown schema key(s) {sorted(map(safe_repr, unknown))}")
    fields = data.get("fields")
    if not isinstance(fields, Mapping) or len(fields) > 10_000:
        raise InvalidSpecError("schema 'fields' must be an object with at most 10,000 columns")
    return {str(k)[:_MAX_NAME]: _validate_override(str(k), v) for k, v in fields.items()}


# ---------------------------------------------------------------- the profiler


def profile(
    data: Any,
    *,
    overrides: Mapping[str, Any] | None = None,
    schema: Any = None,
    hierarchies: bool | Mapping[str, list[str]] = True,
    dayfirst: bool | None = None,
    quiet: bool | None = None,
) -> Profile:
    """Work out the role and unit of every column. The input is never changed."""
    settings = resolve(dayfirst=dayfirst, quiet=quiet)
    frame, notes = _prepare(as_frame(data))
    names = [str(c) for c in frame.columns]

    given: dict[str, dict[str, Any]] = {}
    if schema is not None:
        given.update({k: v for k, v in schema_from_dict(schema).items() if k in names})
    for column, spec in (overrides or {}).items():
        if column not in names:
            raise InvalidSpecError(_unknown_column(column, names))
        given[column] = _validate_override(column, spec)

    fields = []
    for name in names:
        field = _profile_column(name, frame[name], len(frame), settings.dayfirst)
        if name in given:
            field = _apply_override(field, given[name])
        fields.append(field)

    fields, currency_notes = _mixed_currency(fields, frame)
    notes.extend(currency_notes)
    hier = _hierarchies(frame, fields, hierarchies)
    result = Profile(tuple(fields), len(frame), hier, tuple(notes))
    if not settings.quiet:
        for note in currency_notes:
            warn(note, DataWarning)
        for f in result.fields:
            if f.role == "time" and any(r.startswith("day/month order assumed") for r in f.reasons):
                warn(f"{safe_repr(f.name)}: " + f.reasons[-1], ProfileWarning)
    return result


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """A shallow working view with string, unique column names and a meaningful index as a column."""
    notes: list[str] = []
    frame = df
    index = frame.index
    if not isinstance(index, pd.RangeIndex) and (
        index.name is not None or isinstance(index, (pd.DatetimeIndex, pd.MultiIndex))
    ):
        frame = frame.reset_index()
        notes.append("the index was used as column(s)")
    if isinstance(frame.columns, pd.MultiIndex):
        flat = [" / ".join(str(p) for p in col if str(p) != "") for col in frame.columns]
    else:
        flat = [str(c) for c in frame.columns]
    seen: dict[str, int] = {}
    unique = []
    for name in flat:
        name = name[:_MAX_NAME] or "(blank)"
        if name in seen:
            seen[name] += 1
            new = f"{name} ({seen[name]})"
            notes.append(f"duplicate column name {safe_repr(name)} renamed to {safe_repr(new)}")
            unique.append(new)
        else:
            seen[name] = 1
            unique.append(name)
    out = frame.set_axis(unique, axis=1)  # new object; the input is untouched
    return out, notes


def _profile_column(name: str, col: pd.Series, rows: int, dayfirst: bool | None) -> Field:
    words = tokens(name)
    base: dict[str, Any] = {
        "name": name,
        "distinct": int(col.nunique(dropna=True)),
        "missing": int(col.isna().sum()),
        "dtype": str(col.dtype),
    }
    non_null = col.dropna()

    if non_null.empty:
        return Field(role="dimension", source="empty", reasons=("no values",), **base)
    if pd.api.types.is_bool_dtype(col):
        return Field(role="dimension", source="bool", reasons=("true/false values",), **base)
    if pd.api.types.is_datetime64_any_dtype(col):
        reading = read_dates(col)
        if reading is None:  # all values missing after all
            return Field(
                role="time", grain="day", source="datetime", reasons=("datetime column",), **base
            )
        return _time_field(base, reading, "datetime column")
    if pd.api.types.is_timedelta64_dtype(col):
        return Field(
            role="measure", unit="duration", agg="sum", duration_unit="seconds",
            source="timedelta", reasons=("time durations",), **base,
        )  # fmt: skip
    if isinstance(col.dtype, pd.CategoricalDtype) and col.dtype.ordered:
        order = tuple(str(c) for c in col.dtype.categories)
        return Field(
            role="dimension",
            ordered=order,
            source="ordered category",
            reasons=("ordered categorical",),
            **base,
        )
    if pd.api.types.is_numeric_dtype(col):
        return _numeric_field(base, words, non_null, rows)
    return _text_field(base, words, col, non_null, rows, dayfirst)


def _time_field(
    base: dict[str, Any], reading: DateReading, why: str, user_dayfirst: bool = False
) -> Field:
    reasons = [why]
    if reading.format != "datetime":
        reasons.append(f"{reading.success:.0%} parse as {reading.format}")
    if reading.assumed and user_dayfirst:
        reasons.append("day/month order set by dayfirst=" + str(reading.dayfirst))
    elif reading.assumed:
        reasons.append(
            "day/month order assumed "
            + ("day-first" if reading.dayfirst else "month-first")
            + " (no value above 12 settles it; pass dayfirst=)"
        )
    return Field(
        role="time",
        grain=_grain(reading.values),
        date_format=None if reading.format == "datetime" else reading.format,
        dayfirst=reading.dayfirst,
        source="datetime" if reading.format == "datetime" else "text-date",
        reasons=tuple(reasons),
        **base,
    )


def _grain(values: pd.Series) -> str:
    v = values.dropna()
    if v.empty:
        return "day"
    if (v.dt.second != 0).any() or (v.dt.microsecond != 0).any():
        return "second"
    if (v.dt.minute != 0).any():
        return "minute"
    if (v.dt.hour != 0).any():
        return "hour"
    if v.nunique() > 1 and (v.dt.day == 1).all():
        if (v.dt.month == 1).all():
            return "year"
        if v.dt.month.isin([1, 4, 7, 10]).all():
            return "quarter"
        return "month"
    return "day"


def _numeric_field(base: dict[str, Any], words: set[str], values: pd.Series, rows: int) -> Field:
    is_int = pd.api.types.is_integer_dtype(values) or bool((values == values.round()).all())
    lo, hi = float(values.min()), float(values.max())

    if words & _LAT_WORDS and lo >= -90 and hi <= 90:
        return Field(
            role="coord",
            coord="lat",
            source="number",
            reasons=("latitude by name and range",),
            **base,
        )
    if words & _LON_WORDS and lo >= -180 and hi <= 180:
        return Field(
            role="coord",
            coord="lon",
            source="number",
            reasons=("longitude by name and range",),
            **base,
        )
    if words & _YEAR_WORDS and is_int and lo >= 1800 and hi <= 2200:
        return Field(
            role="time",
            grain="year",
            source="integer-year",
            reasons=("whole-number years",),
            **base,
        )
    measure_words = words & (_CURRENCY_WORDS | _PERCENT_WORDS | _COUNT_WORDS)
    if words & _ID_WORDS and not measure_words:
        return Field(
            role="id",
            agg="countd",
            source="number",
            reasons=("name says it is an ID/code; never summed",),
            **base,
        )
    if is_int and base["distinct"] == len(values) and rows >= 20 and not measure_words:
        return Field(
            role="id",
            agg="countd",
            source="number",
            reasons=("every value is different; treated as an ID",),
            **base,
        )
    if is_int and words & _ORDINAL_INT_WORDS and base["distinct"] <= 12:
        order = tuple(str(int(v)) for v in sorted(values.unique()))
        return Field(
            role="dimension",
            ordered=order,
            source="number",
            reasons=("small set of ranked whole numbers",),
            **base,
        )
    return _measure(base, words, values, is_int, source="number")


def _measure(
    base: dict[str, Any],
    words: set[str],
    values: pd.Series,
    is_int: bool,
    source: str,
    unit: str | None = None,
    currency: str | None = None,
    reasons: tuple[str, ...] = (),
) -> Field:
    why = list(reasons)
    duration_unit = None
    named = unit_from_name(base["name"])
    if unit is None and named is not None:
        unit, detail = named
        if unit == "currency":
            currency = detail
        elif unit == "duration":
            duration_unit = detail
        why.append(f"unit written in the name ({unit})")
    if unit is None:
        if words & _PERCENT_WORDS:
            unit = "percent"
            why.append("name suggests a percentage")
        elif words & _CURRENCY_WORDS:
            unit = "currency"
            why.append("name suggests money")
        elif words & _COUNT_WORDS or is_int:
            unit = "count"
            why.append("name suggests a count" if words & _COUNT_WORDS else "whole numbers")
        else:
            unit = "number"
            why.append("plain numbers")
    scale = None
    if unit == "percent":
        lo, hi = float(values.min()), float(values.max())
        scale = "fraction" if lo >= -1.5 and hi <= 1.5 else "whole"
        why.append(
            "values stored as fractions (0.15 = 15%)"
            if scale == "fraction"
            else "values stored as 0-100"
        )
    if unit == "percent" or words & _MEAN_WORDS:
        agg = "mean"
        why.append("averaged, because totals of rates/prices/scores are meaningless")
    else:
        agg = "sum"
    return Field(
        role="measure", unit=unit, agg=agg, currency=currency, percent_scale=scale,
        duration_unit=duration_unit, source=source, reasons=tuple(why), **base,
    )  # fmt: skip


def _text_field(
    base: dict[str, Any],
    words: set[str],
    col: pd.Series,
    values: pd.Series,
    rows: int,
    dayfirst: bool | None,
) -> Field:
    text = values.astype(str)
    if words & _ID_WORDS:
        return Field(
            role="id", agg="countd", source="text", reasons=("name says it is an ID/code",), **base
        )

    reading = read_dates(col, dayfirst=dayfirst)
    if reading is not None:
        return _time_field(
            base, reading, "text that reads as dates", user_dayfirst=dayfirst is not None
        )

    numbers = read_numbers(col)
    if numbers is not None:
        currency = currency_code_for_symbol(numbers.currency_symbol)
        return _measure(
            base, words, numbers.values.dropna(), False, source="text-number",
            unit=numbers.unit, currency=currency,
            reasons=(f"numbers stored as text ({numbers.success:.0%} readable)",),
        )  # fmt: skip

    order = _match_order(text)
    if order is not None:
        return Field(
            role="dimension",
            ordered=order,
            source="text",
            reasons=("known order (months, sizes, levels...)",),
            **base,
        )

    probe = sample(text)
    upper = probe.str.strip().str.upper()
    if base["distinct"] <= 50 and upper.isin(_ISO_CURRENCIES).mean() >= 0.9:
        return Field(
            role="dimension", currency_code_column=True, source="text",
            reasons=("currency codes",), **base,
        )  # fmt: skip
    if rows >= 20 and base["distinct"] == len(values):
        if probe.str.len().mean() > 60:
            return Field(role="text", source="text", reasons=("long free text",), **base)
        return Field(
            role="id",
            agg="countd",
            source="text",
            reasons=("every value is different; treated as an ID",),
            **base,
        )
    if probe.str.len().mean() > 60 and base["distinct"] > 0.5 * len(values):
        return Field(role="text", source="text", reasons=("long free text",), **base)
    return Field(role="dimension", source="text", reasons=("categories",), **base)


def _match_order(text: pd.Series) -> tuple[str, ...] | None:
    distinct = {v.strip().lower() for v in text.unique()[:100]}
    if len(distinct) < 2:
        return None
    for order in _ORDERS:
        if distinct <= set(order):
            originals = {v.strip().lower(): v.strip() for v in text.unique()[:100]}
            return tuple(originals[o] for o in order if o in originals)
    return None


def _apply_override(field: Field, spec: Mapping[str, Any]) -> Field:
    changes: dict[str, Any] = {"overridden": True, "reasons": (*field.reasons, "set by the user")}
    if "role" in spec:
        changes["role"] = spec["role"]
        if spec["role"] == "measure" and field.role != "measure":
            changes.setdefault("unit", "number" if field.unit == "none" else field.unit)
            changes.setdefault("agg", "sum")
        if spec["role"] != "measure":
            changes.update(unit="none", agg="countd" if spec["role"] == "id" else "none")
    for key in ("unit", "agg", "currency", "percent_scale", "date_format", "dayfirst"):
        if key in spec:
            changes[key] = spec[key]
    if "order" in spec:
        changes["ordered"] = tuple(spec["order"])
    return dataclasses.replace(field, **changes)


def _mixed_currency(fields: list[Field], frame: pd.DataFrame) -> tuple[list[Field], list[str]]:
    code_cols = [f for f in fields if f.currency_code_column and f.distinct > 1]
    money = [f for f in fields if f.role == "measure" and f.unit == "currency"]
    notes = []
    for f in money:
        for c in code_cols:
            notes.append(
                f"{safe_repr(f.name)} mixes {c.distinct} currencies (see column {safe_repr(c.name)}); "
                f"it will not be added up across currencies. Filter one currency or use split_by={c.name!r}"
            )
    return fields, notes


def _hierarchies(
    frame: pd.DataFrame, fields: list[Field], option: bool | Mapping[str, list[str]]
) -> tuple[tuple[str, ...], ...]:
    names = {f.name for f in fields}
    if isinstance(option, Mapping):
        out = []
        for label, levels in option.items():
            if not isinstance(levels, list | tuple) or len(levels) < 2:
                raise InvalidSpecError(f"hierarchy {safe_repr(label)} needs a list of 2+ columns")
            for level in levels:
                if level not in names:
                    raise InvalidSpecError(_unknown_column(level, names))
            out.append(tuple(levels))
        return tuple(out)
    if not option:
        return ()
    candidates = [
        f for f in fields
        if f.role == "dimension" and 2 <= f.distinct < MAX_HIERARCHY_DISTINCT
    ][:MAX_HIERARCHY_COLUMNS]  # fmt: skip
    parent_of: dict[str, str] = {}
    for child in candidates:
        best: Field | None = None
        for parent in candidates:
            if parent.distinct >= child.distinct or parent.name == child.name:
                continue
            pair = frame[[parent.name, child.name]].dropna()
            if pair.empty or pair.groupby(child.name, sort=False)[parent.name].nunique().max() != 1:
                continue
            if (
                best is None
                or parent.distinct > best.distinct
                or (parent.distinct == best.distinct and parent.name < best.name)
            ):
                best = parent
        if best is not None:
            parent_of[child.name] = best.name
    children = set(parent_of)
    parents = set(parent_of.values())
    chains = []
    for leaf in sorted(children - parents):
        chain = [leaf]
        while chain[-1] in parent_of and len(chain) <= MAX_HIERARCHY_COLUMNS:
            chain.append(parent_of[chain[-1]])
        chains.append(tuple(reversed(chain)))
    return tuple(sorted(chains))
