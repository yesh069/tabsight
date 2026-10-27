"""Settings, resolved in this order: per call → ``with ts.config(...)`` → ``ts.set_defaults(...)`` → built-in.

``with ts.config(...)`` is stored in a :mod:`contextvars` variable, so concurrent web
requests (threads or async tasks) never see each other's settings. ``ts.set_defaults``
changes the process-wide defaults, typically once at start-up.
"""

from __future__ import annotations

import contextvars
import dataclasses
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["Settings", "config", "current", "reset_defaults", "resolve", "set_defaults"]

_LOCALE_RE = re.compile(r"[a-z]{2}(_[A-Z]{2})?")
_CURRENCY_RE = re.compile(r"[A-Z]{3}")
_TZ_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+\-/]{0,63}")
_WEEK_STARTS = ("monday", "sunday", "saturday")
_MISSING = ("gap", "zero", "connect")


@dataclasses.dataclass(frozen=True)
class Settings:
    """All global options. Every field can also be passed to individual calls."""

    locale: str = "en_US"
    currency: str = "USD"
    dayfirst: bool | None = None  # None: infer from data, then from the locale
    fiscal_start: int = 1  # month the fiscal year starts (1 = calendar year)
    week_start: str = "monday"
    missing: str = "gap"  # missing periods on lines
    tz: str | None = None
    theme: str = "light"
    palette: str = "classic10"
    top: int | None = 10
    strict: bool = False  # turn warnings into errors
    quiet: bool = False  # hide data warnings (errors still raise)
    max_size_mb: float = 5.0
    min_group_size: int | None = None
    csv_safe: bool = True

    def __post_init__(self) -> None:
        _validate(self)

    def replace(self, **changes: Any) -> Settings:
        return dataclasses.replace(self, **changes)


_FIELDS = {f.name for f in dataclasses.fields(Settings)}


def _validate(s: Settings) -> None:
    def bad(name: str, value: Any, expected: str) -> InvalidSpecError:
        return InvalidSpecError(
            f"setting {name}={safe_repr(value)} is invalid: expected {expected}"
        )

    if not isinstance(s.locale, str) or not _LOCALE_RE.fullmatch(s.locale):
        raise bad("locale", s.locale, "a code like 'en_US' or 'de'")
    if not isinstance(s.currency, str) or not _CURRENCY_RE.fullmatch(s.currency):
        raise bad("currency", s.currency, "a 3-letter ISO 4217 code like 'EUR'")
    if s.dayfirst not in (None, True, False):
        raise bad("dayfirst", s.dayfirst, "True, False or None")
    if type(s.fiscal_start) is not int or not 1 <= s.fiscal_start <= 12:
        raise bad("fiscal_start", s.fiscal_start, "a month number 1-12")
    if s.week_start not in _WEEK_STARTS:
        raise bad("week_start", s.week_start, f"one of {_WEEK_STARTS}")
    if s.missing not in _MISSING:
        raise bad("missing", s.missing, f"one of {_MISSING}")
    if s.tz is not None and (not isinstance(s.tz, str) or not _TZ_RE.fullmatch(s.tz)):
        raise bad("tz", s.tz, "a time zone name like 'Europe/Dublin'")
    for name in ("theme", "palette"):
        value = getattr(s, name)
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
            raise bad(name, value, "a lower-case name")
    if s.top is not None and (type(s.top) is not int or not 1 <= s.top <= 1000):
        raise bad("top", s.top, "None or an integer 1-1000")
    for name in ("strict", "quiet", "csv_safe"):
        if not isinstance(getattr(s, name), bool):
            raise bad(name, getattr(s, name), "True or False")
    if not isinstance(s.max_size_mb, int | float) or not 0.1 <= s.max_size_mb <= 1000:
        raise bad("max_size_mb", s.max_size_mb, "a number of megabytes 0.1-1000")
    if s.min_group_size is not None and (
        type(s.min_group_size) is not int or not 2 <= s.min_group_size <= 1000
    ):
        raise bad("min_group_size", s.min_group_size, "None or an integer 2-1000")


def _check_names(kwargs: dict[str, Any]) -> None:
    unknown = sorted(set(kwargs) - _FIELDS)
    if unknown:
        import difflib

        hints = [difflib.get_close_matches(k, _FIELDS, n=1) for k in unknown]
        detail = ", ".join(
            f"{safe_repr(k)}" + (f" (did you mean {h[0]!r}?)" if h else "")
            for k, h in zip(unknown, hints, strict=True)
        )
        raise InvalidSpecError(f"unknown setting(s): {detail}")


_lock = threading.Lock()
_defaults = Settings()
_scoped: contextvars.ContextVar[Settings | None] = contextvars.ContextVar(
    "tabsight_settings", default=None
)


def current() -> Settings:
    """The settings in effect here (scoped settings win over process defaults)."""
    scoped = _scoped.get()
    return scoped if scoped is not None else _defaults


def resolve(**overrides: Any) -> Settings:
    """Current settings with per-call overrides applied (``None`` values are ignored)."""
    given = {k: v for k, v in overrides.items() if v is not None}
    _check_names(given)
    return current().replace(**given) if given else current()


def set_defaults(**kwargs: Any) -> Settings:
    """Change process-wide defaults, for example ``ts.set_defaults(locale="en_IE")``."""
    global _defaults
    _check_names(kwargs)
    with _lock:
        _defaults = _defaults.replace(**kwargs)
        return _defaults


def reset_defaults() -> None:
    """Restore the built-in defaults (mainly for tests)."""
    global _defaults
    with _lock:
        _defaults = Settings()


class config:
    """Scoped settings: ``with ts.config(locale="de_DE"): ...``.

    Only code running in the same thread or async task sees the change. Calling it
    without ``with`` has no effect, so tabsight warns and points to ``set_defaults``.
    """

    def __init__(self, **kwargs: Any) -> None:
        _check_names(kwargs)
        self._kwargs = kwargs
        current().replace(**kwargs)  # validate now, so mistakes fail at the call site
        self._token: contextvars.Token[Settings | None] | None = None
        self._entered = False

    def __enter__(self) -> Settings:
        new = current().replace(**self._kwargs)
        self._token = _scoped.set(new)
        self._entered = True
        return new

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _scoped.reset(self._token)
            self._token = None

    def __del__(self) -> None:
        if not getattr(self, "_entered", True):
            import warnings

            warnings.warn(
                "ts.config(...) only works in a `with` block; "
                "use ts.set_defaults(...) to change settings for the whole program",
                UserWarning,
                stacklevel=2,
            )


@contextmanager
def _scope(settings: Settings) -> Iterator[Settings]:
    """Internal: run code with exact settings (used by dashboards)."""
    token = _scoped.set(settings)
    try:
        yield settings
    finally:
        _scoped.reset(token)
