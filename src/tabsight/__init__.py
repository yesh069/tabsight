"""tabsight: BI-quality charts, world maps and dashboards from a pandas DataFrame.

Rule-based, no LLM, one offline HTML file. See PLAN.md for the roadmap.
"""

from tabsight import warnings
from tabsight._version import __version__
from tabsight.check import CheckReport, check
from tabsight.clean import CleanReport, clean
from tabsight.colors import ColorRegistry
from tabsight.formats import format_date, format_number
from tabsight.io import load
from tabsight.profile import Field, Profile, profile
from tabsight.render.assets import ECHARTS_VERSION, TOPOJSON_CLIENT_VERSION
from tabsight.settings import Settings, config, current, set_defaults
from tabsight.spec import CHART_KINDS, ChartSpec
from tabsight.theme import Theme, custom_theme

__all__ = [
    "CHART_KINDS",
    "ECHARTS_VERSION",
    "TOPOJSON_CLIENT_VERSION",
    "ChartSpec",
    "CheckReport",
    "CleanReport",
    "ColorRegistry",
    "Field",
    "Profile",
    "Settings",
    "Theme",
    "__version__",
    "check",
    "clean",
    "config",
    "current",
    "custom_theme",
    "format_date",
    "format_number",
    "load",
    "profile",
    "set_defaults",
    "warnings",
]
