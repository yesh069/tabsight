"""Bundled JavaScript assets (inlined into HTML so output works offline)."""

from __future__ import annotations

from importlib import resources

# Pinned versions. tools/vendor.lock.json records the source URL and SHA-256 of each file.
ECHARTS_VERSION = "6.1.0"
TOPOJSON_CLIENT_VERSION = "3.1.0"

_STATIC = "tabsight.render.static"


def read_static(name: str) -> str:
    """Return the text of a bundled static file, for example ``"echarts.min.js"``."""
    return resources.files(_STATIC).joinpath(name).read_text(encoding="utf-8")
