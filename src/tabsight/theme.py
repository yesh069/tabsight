"""Themes: light, dark and print. Every theme must pass WCAG AA contrast for its text.

Custom font names are restricted to safe characters, so a theme can never inject CSS.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from tabsight.colors import PALETTES, contrast_ratio, validate_color
from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["THEMES", "Theme", "contrast_problems", "custom_theme", "get_theme"]

SYSTEM_FONTS = (
    '"Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", Arial, sans-serif'
)
_FONT_RE = re.compile(r"[A-Za-z0-9 ,\"'\-]{1,200}")
_COLOR_FIELDS = (
    "page",
    "tile",
    "text",
    "text_secondary",
    "grid",
    "axis",
    "header",
    "border",
    "accent",
)


@dataclasses.dataclass(frozen=True)
class Theme:
    name: str
    page: str
    tile: str
    text: str
    text_secondary: str
    grid: str
    axis: str
    header: str
    border: str
    accent: str
    palette: str = "classic10"
    font: str = SYSTEM_FONTS
    radius: int = 6

    def __post_init__(self) -> None:
        for name in _COLOR_FIELDS:
            object.__setattr__(self, name, validate_color(getattr(self, name)))
        if (
            not _FONT_RE.fullmatch(self.font)
            or self.font.count('"') % 2
            or self.font.count("'") % 2
        ):
            raise InvalidSpecError(
                f"font {safe_repr(self.font)} may only contain letters, digits, spaces, commas, quotes and hyphens"
            )
        if self.palette not in PALETTES:
            raise InvalidSpecError(f"unknown palette {safe_repr(self.palette)}")
        if type(self.radius) is not int or not 0 <= self.radius <= 24:
            raise InvalidSpecError("radius must be an integer 0-24")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", self.name):
            raise InvalidSpecError(
                f"theme name {safe_repr(self.name)} must be a short lower-case name"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


THEMES: dict[str, Theme] = {
    t.name: t
    for t in (
        Theme("light", page="#f4f6f9", tile="#ffffff", text="#1f2329", text_secondary="#5f6670",
              grid="#e9ecef", axis="#c9ced6", header="#f1f3f5", border="#e1e5ea", accent="#4e79a7"),
        Theme("dark", page="#15181d", tile="#1f2329", text="#e8eaed", text_secondary="#a9b0ba",
              grid="#2d333b", axis="#4a525d", header="#262b31", border="#323942", accent="#7aa6d1"),
        Theme("print", page="#ffffff", tile="#ffffff", text="#000000", text_secondary="#444444",
              grid="#dddddd", axis="#999999", header="#f2f2f2", border="#cccccc", accent="#1f4e79",
              palette="okabe_ito", radius=0),
    )
}  # fmt: skip


def get_theme(name: str) -> Theme:
    if name not in THEMES:
        raise InvalidSpecError(f"unknown theme {safe_repr(name)}; choose from {sorted(THEMES)}")
    return THEMES[name]


def custom_theme(base: str = "light", **changes: Any) -> Theme:
    """A theme based on a built-in one, for example brand colours. Contrast is checked."""
    unknown = set(changes) - {f.name for f in dataclasses.fields(Theme)}
    if unknown:
        raise InvalidSpecError(f"unknown theme field(s) {sorted(map(safe_repr, unknown))}")
    theme = dataclasses.replace(get_theme(base), **changes)
    problems = contrast_problems(theme)
    if problems:
        raise InvalidSpecError("theme fails WCAG AA contrast: " + "; ".join(problems))
    return theme


def contrast_problems(theme: Theme) -> list[str]:
    """Text/background pairs below WCAG AA (4.5:1)."""
    pairs = [
        ("text", "tile"),
        ("text", "page"),
        ("text", "header"),
        ("text_secondary", "tile"),
        ("text_secondary", "header"),
    ]
    out = []
    for fg, bg in pairs:
        ratio = contrast_ratio(getattr(theme, fg), getattr(theme, bg))
        if ratio < 4.5:
            out.append(f"{fg} on {bg} is {ratio:.2f}:1")
    return out
