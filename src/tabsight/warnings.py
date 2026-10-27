"""tabsight warning and error types, plus safe display of untrusted values in messages.

Users can filter tabsight warnings with the standard library, for example::

    import warnings, tabsight
    warnings.simplefilter("ignore", tabsight.warnings.CleanWarning)
"""

from __future__ import annotations

import warnings as _stdlib_warnings
from typing import Any

__all__ = [
    "CleanWarning",
    "DataWarning",
    "FormatWarning",
    "InvalidSpecError",
    "ProfileWarning",
    "TabsightError",
    "TabsightWarning",
    "UnsafeInputError",
    "safe_repr",
    "warn",
]


class TabsightWarning(UserWarning):
    """Base class for every warning tabsight emits."""


class DataWarning(TabsightWarning):
    """Something about the input data that may give misleading charts."""


class ProfileWarning(TabsightWarning):
    """A guess made while reading the data (role, unit, date order...)."""


class CleanWarning(TabsightWarning):
    """Something the optional cleaning step changed or suggests."""


class FormatWarning(TabsightWarning):
    """A formatting fallback (unknown locale, unknown currency...)."""


class TabsightError(Exception):
    """Base class for every error tabsight raises."""


class InvalidSpecError(TabsightError, ValueError):
    """A saved spec, schema or option failed validation."""


class UnsafeInputError(TabsightError, ValueError):
    """Input rejected for safety reasons (for example a URL instead of a local file)."""


_MAX_REPR = 60


def safe_repr(value: Any, limit: int = _MAX_REPR) -> str:
    """repr() of an untrusted value, shortened, for use in messages.

    repr() escapes control characters and quotes strings, so data cannot fake extra
    message lines or flood the console.
    """
    try:
        text = repr(value)
    except Exception:  # a hostile __repr__ must not break error reporting
        text = f"<{type(value).__name__}>"
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def warn(
    message: str, category: type[TabsightWarning] = TabsightWarning, stacklevel: int = 3
) -> None:
    """Emit a tabsight warning, or raise it as an error when strict mode is on."""
    from tabsight.settings import current

    if current().strict:
        raise TabsightError(f"{category.__name__}: {message}")
    _stdlib_warnings.warn(message, category, stacklevel=stacklevel)
