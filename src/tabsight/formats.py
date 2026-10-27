"""Number, currency, percent, duration and date formatting for every locale tabsight supports.

Three styles: ``compact`` (axes, KPI cards: ``$2.3M``), ``full`` (tooltips, tables:
``$2,297,201``) and ``raw`` (exports: ``2297200.86``). Rounding is half-up on the
shortest decimal form of the number, which the JavaScript runtime copies exactly.

Custom patterns (``"#,##0.0"``, ``"0.0%"``, ``'"€"#,##0'``) go through a small strict
parser; user text is never passed to ``str.format``.
"""

from __future__ import annotations

import dataclasses
import math
import re
from decimal import ROUND_HALF_UP, Context, Decimal
from typing import Any

import pandas as pd

from tabsight.i18n import month_name
from tabsight.settings import resolve
from tabsight.warnings import FormatWarning, InvalidSpecError, safe_repr, warn

__all__ = [
    "LOCALES",
    "Locale",
    "choose_decimals",
    "currency_symbol",
    "format_date",
    "format_number",
    "get_locale",
    "parse_pattern",
]

NBSP = " "
NNBSP = " "
STYLES = ("compact", "full", "raw")
NUMBER_UNITS = ("currency", "percent", "pp", "count", "number", "duration", "none")


@dataclasses.dataclass(frozen=True)
class Locale:
    code: str
    lang: str
    decimal: str
    group: str
    grouping: tuple[int, ...]  # (3,) or Indian (3, 2)
    currency_before: bool
    currency_space: bool
    percent_space: bool
    compact: tuple[tuple[float, str], ...]  # (threshold, suffix), largest first
    compact_space: bool
    dayfirst: bool
    day_month_order: str  # "mdy" or "dmy" for written dates


_EN = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"))
LOCALES: dict[str, Locale] = {
    loc.code: loc
    for loc in (
        Locale("en_US", "en", ".", ",", (3,), True, False, False, _EN, False, False, "mdy"),
        Locale("en_GB", "en", ".", ",", (3,), True, False, False, _EN, False, True, "dmy"),
        Locale("en_IE", "en", ".", ",", (3,), True, False, False, _EN, False, True, "dmy"),
        Locale("en_AU", "en", ".", ",", (3,), True, False, False, _EN, False, True, "dmy"),
        Locale("en_CA", "en", ".", ",", (3,), True, False, False, _EN, False, False, "mdy"),
        Locale("en_IN", "en", ".", ",", (3, 2), True, False, False, ((1e7, "Cr"), (1e5, "L"), (1e3, "K")), False, True, "dmy"),
        Locale("de_DE", "de", ",", ".", (3,), False, True, True, ((1e9, "Mrd."), (1e6, "Mio."), (1e3, "Tsd.")), True, True, "dmy"),
        Locale("de_AT", "de", ",", NBSP, (3,), True, True, True, ((1e9, "Mrd."), (1e6, "Mio."), (1e3, "Tsd.")), True, True, "dmy"),
        Locale("fr_FR", "fr", ",", NNBSP, (3,), False, True, True, ((1e9, "Md"), (1e6, "M"), (1e3, "k")), True, True, "dmy"),
        Locale("es_ES", "es", ",", ".", (3,), False, True, True, ((1e9, "mil M"), (1e6, "M"), (1e3, "mil")), True, True, "dmy"),
        Locale("it_IT", "it", ",", ".", (3,), False, True, False, ((1e9, "Mrd"), (1e6, "Mln"), (1e3, "K")), True, True, "dmy"),
        Locale("nl_NL", "nl", ",", ".", (3,), True, True, False, ((1e9, "mld."), (1e6, "mln."), (1e3, "K")), True, True, "dmy"),
        Locale("pt_BR", "pt", ",", ".", (3,), True, True, False, ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")), True, True, "dmy"),
        Locale("pt_PT", "pt", ",", NBSP, (3,), False, True, False, ((1e9, "mM"), (1e6, "M"), (1e3, "mil")), True, True, "dmy"),
    )
}  # fmt: skip
_LANG_DEFAULT = {
    "en": "en_US",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
    "it": "it_IT",
    "nl": "nl_NL",
    "pt": "pt_BR",
}

_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "CNY": "CN¥", "AUD": "A$", "CAD": "CA$",
    "CHF": "CHF", "BRL": "R$", "KRW": "₩", "RUB": "₽", "MXN": "MX$", "SGD": "S$", "HKD": "HK$",
    "NZD": "NZ$", "ZAR": "R", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł", "TRY": "₺",
    "ILS": "₪", "THB": "฿", "NGN": "₦", "PHP": "₱", "VND": "₫",
}  # fmt: skip
_LOCAL_SYMBOL = {("en_AU", "AUD"): "$", ("en_CA", "CAD"): "$"}
_ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF"}


def get_locale(code: str | None = None) -> Locale:
    code = code or resolve().locale
    if code in LOCALES:
        return LOCALES[code]
    lang = code.split("_")[0]
    fallback = _LANG_DEFAULT.get(lang, "en_US")
    warn(f"locale {safe_repr(code)} is not built in; using {fallback}", FormatWarning)
    return LOCALES[fallback]


def currency_symbol(code: str, locale: Locale) -> str:
    if (locale.code, code) in _LOCAL_SYMBOL:
        return _LOCAL_SYMBOL[(locale.code, code)]
    return _SYMBOLS.get(code, code + NBSP)


# ---------------------------------------------------------------- core number helpers


# Enough digits for any float (max ~1.8e308) plus 6 decimals.
_DECIMAL_CONTEXT = Context(prec=400, rounding=ROUND_HALF_UP)


class _NotFinite(Exception):
    """A value became infinite while scaling (for example 1e307 shown as a percent)."""


def _round(value: float, decimals: int) -> Decimal:
    """Half-up rounding of the shortest decimal form (what people expect: 2.5 → 3)."""
    if not math.isfinite(value):
        raise _NotFinite
    return Decimal(repr(float(value))).quantize(
        Decimal(1).scaleb(-decimals), context=_DECIMAL_CONTEXT
    )


def _group(digits: str, locale: Locale) -> str:
    if len(digits) <= 3 or not locale.group:
        return digits
    first, *rest = locale.grouping
    head, tail = digits[:-first], digits[-first:]
    size = rest[0] if rest else first
    parts = [tail]
    while head:
        parts.append(head[-size:])
        head = head[:-size]
    return locale.group.join(reversed(parts))


def _fixed(
    value: float, decimals: int, locale: Locale, grouped: bool = True, strip: bool = False
) -> str:
    rounded = _round(abs(value), decimals)
    text = f"{rounded:f}"
    whole, _, frac = text.partition(".")
    if strip:
        frac = frac.rstrip("0")
    whole = _group(whole, locale) if grouped else whole
    return whole + (locale.decimal + frac if frac else "")


def _compact(value: float, locale: Locale, decimals: int = 1) -> str:
    v = abs(value)
    for i, (threshold, suffix) in enumerate(locale.compact):
        if v >= threshold:
            scaled = _round(v / threshold, decimals)
            # promote after rounding: 999.95K → 1M
            if i > 0 and scaled >= Decimal(int(locale.compact[i - 1][0] / threshold)):
                bigger, big_suffix = locale.compact[i - 1]
                text = _fixed(v / bigger, decimals, locale, strip=True)
                return text + (NBSP if locale.compact_space else "") + big_suffix
            text = _fixed(v / threshold, decimals, locale, strip=True)
            return text + (NBSP if locale.compact_space else "") + suffix
    if v == int(v):
        return _fixed(v, 0, locale)
    return _fixed(v, 2 if v < 10 else 1, locale, strip=True)


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        return math.isnan(value) or math.isinf(value)
    except TypeError:
        return False


# ---------------------------------------------------------------- patterns

_PATTERN_RE = re.compile(
    r'(?P<prefix>"[^"\x00-\x1f]{0,12}"|[$€£¥₹₩₽])?'
    r"(?P<int>[#0,]{0,20}0)"
    r"(?:\.(?P<dec>0{1,6}))?"
    r'(?P<suffix>%|"[^"\x00-\x1f]{0,12}")?'
)


@dataclasses.dataclass(frozen=True)
class Pattern:
    prefix: str
    decimals: int
    grouped: bool
    percent: bool
    suffix: str


def parse_pattern(pattern: str) -> Pattern:
    """Parse a small Excel-style pattern: ``#,##0``, ``0.0%``, ``"€"#,##0.00``, ``0.0" kg"``."""
    if not isinstance(pattern, str) or len(pattern) > 60:
        raise InvalidSpecError("format pattern must be a short string")
    m = _PATTERN_RE.fullmatch(pattern)
    if not m:
        raise InvalidSpecError(
            f"format pattern {safe_repr(pattern)} is not supported; use forms like '#,##0', '0.0%', '\"€\"#,##0.00'"
        )
    prefix = (m["prefix"] or "").strip('"')
    suffix = m["suffix"] or ""
    return Pattern(
        prefix=prefix,
        decimals=len(m["dec"] or ""),
        grouped="," in m["int"],
        percent=suffix == "%",
        suffix="%" if suffix == "%" else suffix.strip('"'),
    )


# ---------------------------------------------------------------- public formatting


def format_number(
    value: Any,
    unit: str = "number",
    style: str = "full",
    *,
    locale: str | None = None,
    currency: str | None = None,
    decimals: int | None = None,
    percent_scale: str = "fraction",
    duration_unit: str = "seconds",
    negative: str = "minus",
    sign: bool = False,
    pattern: str | None = None,
) -> str:
    """Format one value. Missing, NaN and infinite values give ``""``."""
    if style not in STYLES:
        raise InvalidSpecError(f"style must be one of {STYLES}")
    if unit not in NUMBER_UNITS:
        raise InvalidSpecError(f"unit must be one of {NUMBER_UNITS}")
    if decimals is not None and (type(decimals) is not int or not 0 <= decimals <= 6):
        raise InvalidSpecError("decimals must be an integer 0-6")
    if negative not in ("minus", "parens"):
        raise InvalidSpecError("negative must be 'minus' or 'parens'")
    if _is_missing(value):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InvalidSpecError(f"cannot format {safe_repr(value)} as a number") from None
    if style == "raw":
        return repr(number) if number != int(number) else str(int(number))
    try:
        return _format_valid(
            number, unit, style, locale, currency, decimals,
            percent_scale, duration_unit, negative, sign, pattern,
        )  # fmt: skip
    except _NotFinite:
        return ""


def _format_valid(
    number: float,
    unit: str,
    style: str,
    locale: str | None,
    currency: str | None,
    decimals: int | None,
    percent_scale: str,
    duration_unit: str,
    negative: str,
    sign: bool,
    pattern: str | None,
) -> str:
    loc = get_locale(locale)
    if pattern is not None:
        body = _with_pattern(number, parse_pattern(pattern), loc)
        return _signed(body, number, negative, sign)

    if unit == "percent" or unit == "pp":
        shown = number * 100 if percent_scale == "fraction" else number
        d = decimals if decimals is not None else 1
        text = _fixed(shown, d, loc, strip=decimals is None)
        suffix = " pp" if unit == "pp" else ((NBSP if loc.percent_space else "") + "%")
        return _signed(text + suffix, shown, negative, sign or unit == "pp")

    if unit == "duration":
        return _signed(_duration(abs(number), duration_unit, loc), number, negative, sign)

    if unit == "currency":
        code = currency or resolve().currency
        symbol = currency_symbol(code, loc)
        if style == "compact":
            body = _compact(number, loc)
        else:
            d = (
                decimals
                if decimals is not None
                else (0 if code in _ZERO_DECIMAL or abs(number) >= 1000 else 2)
            )
            body = _fixed(number, d, loc)
        space = NBSP if loc.currency_space else ""
        body = symbol + space + body if loc.currency_before else body + space + symbol.strip()
        return _signed(body, number, negative, sign)

    if style == "compact":
        return _signed(_compact(number, loc), number, negative, sign)
    if unit == "count":
        d = decimals if decimals is not None else 0
        return _signed(_fixed(number, d, loc), number, negative, sign)
    d = decimals if decimals is not None else (0 if number == int(number) else 2)
    return _signed(_fixed(number, d, loc, strip=decimals is None and d > 0), number, negative, sign)


_NONZERO_DIGIT = re.compile(r"[1-9]")


def _signed(body: str, number: float, negative: str, sign: bool) -> str:
    if number < 0 and _NONZERO_DIGIT.search(body):  # no "-0" when the value rounds to zero
        return f"({body})" if negative == "parens" else "-" + body
    if sign and number > 0:
        return "+" + body
    return body


def _with_pattern(number: float, p: Pattern, loc: Locale) -> str:
    shown = abs(number) * (100 if p.percent else 1)
    return p.prefix + _fixed(shown, p.decimals, loc, grouped=p.grouped) + p.suffix


_DURATION_SECONDS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}


def _duration(value: float, unit: str, loc: Locale) -> str:
    if unit not in _DURATION_SECONDS:
        raise InvalidSpecError(f"duration unit must be one of {tuple(_DURATION_SECONDS)}")
    seconds = value * _DURATION_SECONDS[unit]
    if seconds >= 2 * 86400:
        return _fixed(seconds / 86400, 1, loc, strip=True) + " days"
    whole = int(
        _round(seconds, 0)
    )  # half-up, like every other number (Python's round() is half-even)
    if seconds >= 3600:
        h, rem = divmod(whole, 3600)
        return f"{h}h {rem // 60}m"
    if seconds >= 60:
        m, s = divmod(whole, 60)
        return f"{m}m {s}s"
    return _fixed(seconds, 0 if seconds >= 10 else 1, loc, strip=True) + "s"


def choose_decimals(values: Any, unit: str = "number") -> int:
    """One decimal setting for a whole column, so a table lines up."""
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    series = series[series.map(math.isfinite)]
    if series.empty:
        return 0
    if unit in ("count",) or bool((series == series.round()).all()):
        return 0
    if series.abs().max() >= 1000:
        return 0
    return 2 if unit == "currency" or series.abs().max() < 100 else 1


# ---------------------------------------------------------------- dates

DATE_GRAINS = ("year", "quarter", "month", "week", "day", "hour", "minute", "second")


def format_date(
    value: Any,
    grain: str = "day",
    style: str = "full",
    *,
    locale: str | None = None,
    fiscal_start: int | None = None,
) -> str:
    """``2017``, ``Q1 2017`` / ``FY2018 Q1``, ``Jan 2017`` (axis: ``Jan '17``), ``Jan 5, 2017``."""
    if grain not in DATE_GRAINS:
        raise InvalidSpecError(f"grain must be one of {DATE_GRAINS}")
    if _is_missing(value):
        return ""
    ts = pd.Timestamp(value)
    loc = get_locale(locale)
    fs = fiscal_start if fiscal_start is not None else resolve().fiscal_start
    mon = month_name(ts.month, loc.lang, short=True)
    if grain == "year":
        if fs != 1:
            return f"FY{_fiscal_year(ts, fs)}"
        return str(ts.year)
    if grain == "quarter":
        if fs != 1:
            q = ((ts.month - fs) % 12) // 3 + 1
            return f"FY{_fiscal_year(ts, fs)} Q{q}"
        return f"Q{(ts.month - 1) // 3 + 1} {ts.year}"
    if grain == "month":
        if style == "compact":
            return f"{mon} '{ts.year % 100:02d}"
        return f"{mon} {ts.year}"
    if grain == "week":
        iso = ts.isocalendar()
        return f"W{iso.week:02d} {iso.year}"
    day = (
        f"{mon} {ts.day}, {ts.year}"
        if loc.day_month_order == "mdy"
        else f"{ts.day} {mon} {ts.year}"
    )
    if style == "compact" and grain == "day":
        day = f"{mon} {ts.day}" if loc.day_month_order == "mdy" else f"{ts.day} {mon}"
    if grain == "day":
        return day
    if grain == "hour":
        return f"{day} {ts.hour:02d}:00"
    if grain == "minute":
        return f"{day} {ts.hour:02d}:{ts.minute:02d}"
    return f"{day} {ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"


def _fiscal_year(ts: pd.Timestamp, fiscal_start: int) -> int:
    """Fiscal years are named by the calendar year they end in (FY2018 = Apr 2017 - Mar 2018)."""
    return ts.year + 1 if ts.month >= fiscal_start else ts.year


# ---------------------------------------------------------------- browser runtime support


def locale_payload(codes: Any) -> dict[str, dict[str, Any]]:
    """The locale data the browser runtime needs, for the given locale codes only."""
    out: dict[str, dict[str, Any]] = {}
    for code in sorted(set(codes)):
        loc = get_locale(code)
        out[loc.code] = {
            "decimal": loc.decimal,
            "group": loc.group,
            "grouping": list(loc.grouping),
            "currency_before": loc.currency_before,
            "currency_space": loc.currency_space,
            "percent_space": loc.percent_space,
            "compact": [[threshold, suffix] for threshold, suffix in loc.compact],
            "compact_space": loc.compact_space,
        }
    return out


def js_spec(
    unit: str = "number",
    style: str = "full",
    *,
    locale: str | None = None,
    currency: str | None = None,
    decimals: int | None = None,
    percent_scale: str = "fraction",
    duration_unit: str = "seconds",
    negative: str = "minus",
    sign: bool = False,
    pattern: str | None = None,
) -> dict[str, Any]:
    """A JSON-safe description of a number format, for ``tabsight.js``.

    Validated here exactly like ``format_number``; the browser only receives plain data
    (symbols resolved, patterns already parsed), never code.
    """
    format_number(0, unit, style, locale=locale, currency=currency, decimals=decimals,
                  percent_scale=percent_scale, duration_unit=duration_unit,
                  negative=negative, sign=sign, pattern=pattern)  # fmt: skip
    loc = get_locale(locale)
    code = currency or resolve().currency
    spec: dict[str, Any] = {
        "unit": unit,
        "style": style,
        "locale": loc.code,
        "decimals": decimals,
        "percent_scale": percent_scale,
        "duration_unit": duration_unit,
        "negative": negative,
        "sign": sign,
        "currency_symbol": currency_symbol(code, loc),
        "zero_decimal": code in _ZERO_DECIMAL,
    }
    if pattern is not None:
        spec["pattern"] = dataclasses.asdict(parse_pattern(pattern))
    return spec
