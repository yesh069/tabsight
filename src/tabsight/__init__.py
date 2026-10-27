"""tabsight: BI-quality charts, world maps and dashboards from a pandas DataFrame.

Rule-based, no LLM, one offline HTML file. See PLAN.md for the roadmap.
"""

from tabsight import geo, warnings
from tabsight._version import __version__
from tabsight.aggregate import Aggregation, Measure, aggregate, bucket
from tabsight.charts import chart
from tabsight.check import CheckReport, check
from tabsight.clean import CleanReport, clean
from tabsight.colors import ColorRegistry
from tabsight.figure import Figure
from tabsight.formats import format_date, format_number
from tabsight.formulas import CalcField, calc
from tabsight.io import load
from tabsight.lint import LintIssue, LintReport
from tabsight.profile import Field, Profile, profile
from tabsight.recommend import Recommendation, Recommendations, recommend
from tabsight.render.assets import ECHARTS_VERSION, TOPOJSON_CLIENT_VERSION, runtime_js
from tabsight.settings import Settings, config, current, set_defaults
from tabsight.spec import CHART_KINDS, ChartSpec
from tabsight.tablecalc import table_calc
from tabsight.theme import Theme, custom_theme

__all__ = [
    "CHART_KINDS",
    "ECHARTS_VERSION",
    "TOPOJSON_CLIENT_VERSION",
    "Aggregation",
    "CalcField",
    "ChartSpec",
    "CheckReport",
    "CleanReport",
    "ColorRegistry",
    "Field",
    "Figure",
    "LintIssue",
    "LintReport",
    "Measure",
    "Profile",
    "Recommendation",
    "Recommendations",
    "Settings",
    "Theme",
    "__version__",
    "aggregate",
    "bucket",
    "calc",
    "chart",
    "check",
    "clean",
    "config",
    "current",
    "custom_theme",
    "format_date",
    "format_number",
    "geo",
    "load",
    "profile",
    "recommend",
    "runtime_js",
    "set_defaults",
    "table_calc",
    "warnings",
]
