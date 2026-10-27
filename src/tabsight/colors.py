"""Palettes, a colour registry (same value → same colour everywhere) and contrast checks.

Every colour a user supplies is validated as a hex code, so a colour value can never
inject CSS or markup into the HTML output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = [
    "DIVERGING",
    "PALETTES",
    "SEQUENTIAL",
    "ColorRegistry",
    "contrast_ratio",
    "natural_key",
    "text_color_on",
    "validate_color",
]

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")

PALETTES: dict[str, tuple[str, ...]] = {
    # Same colours as d3's schemeTableau10, a widely used categorical palette.
    "classic10": (
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    ),
    # Okabe & Ito (2008), designed to be distinguishable with colour-vision deficiency.
    "okabe_ito": ("#0072b2", "#e69f00", "#009e73", "#cc79a7", "#56b4e9", "#d55e00", "#f0e442", "#000000"),
    "muted": ("#5778a4", "#e49444", "#d1615d", "#85b6b2", "#6a9f58", "#e7ca60", "#a87c9f", "#f1a2a9"),
}  # fmt: skip
SEQUENTIAL: dict[str, tuple[str, ...]] = {
    "blues": ("#dbe9f6", "#9ecae1", "#6baed6", "#3182bd", "#1f3b5c"),
    "greens": ("#e5f5e0", "#a1d99b", "#74c476", "#31a354", "#1b5e20"),
}
DIVERGING: dict[str, tuple[str, ...]] = {
    "red_blue": ("#c0392b", "#e15759", "#f7f7f7", "#7aa6d1", "#4e79a7"),
}
SINGLE_SERIES = "#4e79a7"


def validate_color(value: Any) -> str:
    """Return a normalised lower-case hex colour, or raise InvalidSpecError."""
    if not isinstance(value, str) or not _HEX_RE.fullmatch(value.strip()):
        raise InvalidSpecError(f"colour {safe_repr(value)} must be a hex code like '#4e79a7'")
    return value.strip().lower()


_NUM_SPLIT = re.compile(r"(\d+)")


def natural_key(value: Any) -> tuple[Any, ...]:
    """Sort key where 'Item 2' comes before 'Item 10'."""
    text = str(value)[:200].lower()
    return tuple(int(p) if p.isdigit() else p for p in _NUM_SPLIT.split(text))


class ColorRegistry:
    """Assigns palette colours to values, stably: values are sorted before assignment,
    so the same data always gets the same colours regardless of row order."""

    def __init__(
        self, palette: str | Iterable[str] = "classic10", pinned: Mapping[str, str] | None = None
    ) -> None:
        if isinstance(palette, str):
            if palette not in PALETTES:
                raise InvalidSpecError(
                    f"unknown palette {safe_repr(palette)}; choose from {sorted(PALETTES)}"
                )
            self.palette = PALETTES[palette]
            self.palette_name: str | None = palette
        else:
            colors = tuple(validate_color(c) for c in palette)
            if not 1 <= len(colors) <= 64:
                raise InvalidSpecError("a custom palette needs 1-64 colours")
            self.palette, self.palette_name = colors, None
        if pinned is not None and len(pinned) > 10_000:
            raise InvalidSpecError("too many pinned colours")
        self._colors: dict[str, str] = {
            str(k)[:200]: validate_color(v) for k, v in (pinned or {}).items()
        }
        self._pinned = set(self._colors)
        self._next = 0

    def assign(self, values: Iterable[Any]) -> None:
        """Give colours to new values, in natural sort order."""
        new = sorted(
            {str(v)[:200] for v in values if str(v)[:200] not in self._colors}, key=natural_key
        )
        for value in new:
            self._colors[value] = self.palette[self._next % len(self.palette)]
            self._next += 1

    def color(self, value: Any) -> str:
        key = str(value)[:200]
        if key not in self._colors:
            self.assign([key])
        return self._colors[key]

    def mapping(self) -> dict[str, str]:
        return dict(self._colors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "palette": self.palette_name or list(self.palette),
            "colors": dict(self._colors),
            "pinned": sorted(self._pinned),
        }

    @classmethod
    def from_dict(cls, data: Any) -> ColorRegistry:
        if not isinstance(data, Mapping) or set(data) - {"palette", "colors", "pinned"}:
            raise InvalidSpecError(
                "colour registry must have only 'palette', 'colors' and 'pinned'"
            )
        colors = data.get("colors", {})
        if not isinstance(colors, Mapping):
            raise InvalidSpecError("'colors' must map values to hex colours")
        reg = cls(data.get("palette", "classic10"), pinned=colors)
        pinned = data.get("pinned", [])
        if not isinstance(pinned, list):
            raise InvalidSpecError("'pinned' must be a list")
        reg._pinned = {str(p)[:200] for p in pinned} & set(reg._colors)
        reg._next = len(reg._colors) - len(reg._pinned)
        return reg


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    hexpart = validate_color(color)[1:]
    if len(hexpart) in (3, 4):
        hexpart = "".join(ch * 2 for ch in hexpart[:3])
    r, g, b = (int(hexpart[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours (1-21). Text needs 4.5 for AA."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_color_on(background: str, dark: str = "#1f2329", light: str = "#ffffff") -> str:
    """Dark or light text, whichever contrasts more with ``background``."""
    return dark if contrast_ratio(background, dark) >= contrast_ratio(background, light) else light
