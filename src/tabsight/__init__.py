"""tabsight: BI-quality charts, world maps and dashboards from a pandas DataFrame.

Rule-based, no LLM, one offline HTML file. See PLAN.md for the roadmap.
"""

from tabsight._version import __version__
from tabsight.render.assets import ECHARTS_VERSION, TOPOJSON_CLIENT_VERSION

__all__ = ["ECHARTS_VERSION", "TOPOJSON_CLIENT_VERSION", "__version__"]
