"""tabsight: BI-quality charts, world maps and dashboards from a pandas DataFrame.

One offline HTML file. Docs: https://yesh069.github.io/tabsight/
"""

from tabsight import analytics, geo, warnings, web
from tabsight._version import __version__
from tabsight.accessor import register as _register_accessors
from tabsight.aggregate import Aggregation, Measure, aggregate, bucket
from tabsight.auto import auto
from tabsight.charts import chart
from tabsight.check import CheckReport, check
from tabsight.clean import CleanReport, clean
from tabsight.colors import ColorRegistry
from tabsight.dashboard import Dashboard
from tabsight.figure import Figure
from tabsight.formats import format_date, format_number
from tabsight.formulas import CalcField, calc
from tabsight.insight import Insight, Insights, insights
from tabsight.io import load
from tabsight.lint import LintIssue, LintReport
from tabsight.periods import Comparison, compare
from tabsight.plotting import plot  # also lets pandas find the backend without the entry point
from tabsight.profile import Field, Profile, profile
from tabsight.recommend import Recommendation, Recommendations, recommend
from tabsight.render.assets import ECHARTS_VERSION, TOPOJSON_CLIENT_VERSION, runtime_js
from tabsight.server import DashboardServer
from tabsight.settings import Settings, config, current, set_defaults
from tabsight.spec import CHART_KINDS, ChartSpec
from tabsight.tablecalc import table_calc
from tabsight.theme import Theme, custom_theme
from tabsight.web import serve_payload, streamlit

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
    "Comparison",
    "Dashboard",
    "DashboardServer",
    "Field",
    "Figure",
    "Insight",
    "Insights",
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
    "analytics",
    "auto",
    "bucket",
    "calc",
    "chart",
    "check",
    "clean",
    "compare",
    "config",
    "current",
    "custom_theme",
    "format_date",
    "format_number",
    "geo",
    "insights",
    "load",
    "plot",
    "profile",
    "recommend",
    "runtime_js",
    "serve_payload",
    "set_defaults",
    "streamlit",
    "table_calc",
    "warnings",
    "web",
]

_register_accessors()  # df.ts and series.ts
