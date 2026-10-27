"""Figure: a finished chart, as plain JSON plus ways to show it."""

from __future__ import annotations

import copy
import dataclasses
import html
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tabsight.render.html import page, srcdoc_iframe
from tabsight.spec import ChartSpec
from tabsight.theme import THEMES, Theme
from tabsight.warnings import InvalidSpecError, safe_repr

if TYPE_CHECKING:
    from tabsight.lint import LintReport

__all__ = ["FIGURE_VERSION", "Figure"]

FIGURE_VERSION = 1
NOTEBOOK_TIP_BYTES = 10_000_000
PICTURE_MAX_BYTES = 2_000_000  # a bigger picture would bloat the notebook more than it helps
_NOTEBOOK = {"bytes": 0, "tipped": 0}  # charts shown in this Python session
_MAX_PATCH_DEPTH = 20


@dataclasses.dataclass(frozen=True)
class Figure:
    """A chart ready to display. ``to_dict()`` is plain JSON for any web page that loads
    ``tabsight.js``; ``to_html()`` writes a single offline file."""

    kind: str
    spec: ChartSpec
    title: str
    subtitle: str | None = None
    option: dict[str, Any] | None = None
    kpi: dict[str, Any] | None = None
    table: dict[str, Any] | None = None
    locales: dict[str, Any] = dataclasses.field(default_factory=dict)
    theme: Theme = THEMES["light"]
    height: int = 420
    notes: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()  # why the chart looks the way it does; see explain()
    maps: tuple[
        dict[str, Any], ...
    ] = ()  # shapes a map needs (TopoJSON), registered in the browser
    facts: dict[str, Any] = dataclasses.field(default_factory=dict)  # what lint() checks
    insights: tuple[dict[str, Any], ...] = ()  # plain-English facts, when insights=True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tabsight_figure": FIGURE_VERSION,
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "theme": self.theme.to_dict(),
            "height": self.height,
            "notes": list(self.notes),
            "spec": self.spec.to_dict(),
            "locales": self.locales,
        }
        if self.option is not None:
            out["option"] = self.option
        if self.kpi is not None:
            out["kpi"] = self.kpi
        if self.table is not None:
            out["table"] = self.table
        if self.maps:
            out["maps"] = list(self.maps)
        if self.insights:
            out["insights"] = [{"text": i["text"], "scope": i["scope"]} for i in self.insights]
        return out

    def to_html(self, path: str | Path | None = None, *, cdn: bool = False) -> str:
        """The chart as one HTML document. Writes it to ``path`` if given.

        Offline by default (ECharts is inlined, about 1.1 MB). ``cdn=True`` loads ECharts
        from jsDelivr instead, pinned with a Subresource Integrity hash.
        """
        document = page(self.to_dict(), self.theme, cdn=cdn)
        if path is not None:
            Path(path).write_text(document, encoding="utf-8")
        return document

    def _repr_html_(self) -> str:
        """Jupyter display: the page inside a sandboxed iframe, isolated from the notebook.

        Each chart carries its own copy of ECharts (about 1 MB) so it works offline. Once a
        session has shown about 10 MB of charts, a one-time tip suggests ``ts.set_defaults(cdn=True)``.
        """
        from tabsight.settings import current

        cdn = current().cdn
        document = self.to_html(cdn=cdn)
        if not cdn:
            _NOTEBOOK["bytes"] += len(document)
            if _NOTEBOOK["bytes"] > NOTEBOOK_TIP_BYTES and not _NOTEBOOK["tipped"]:
                _NOTEBOOK["tipped"] = 1
                import warnings

                from tabsight.warnings import TabsightWarning

                # shown while IPython displays the cell, so no line of user code to point at

                warnings.warn_explicit(
                    "this notebook now holds over 10 MB of charts, because each one carries ECharts so it "
                    "works offline; ts.set_defaults(cdn=True) loads it from the internet instead (pinned by hash)",
                    TabsightWarning, "tabsight", 0,

                )  # fmt: skip
        extra = (150 if self.kind not in ("kpi", "table") else 260) + _notes_height(self.notes)
        if self.insights:
            extra += 40 + _notes_height(tuple(i["text"] for i in self.insights))
        frame = srcdoc_iframe(document, self.height + extra)
        picture = self._picture() if current().picture else None
        if picture is None:
            return frame
        # The picture and the live chart share one grid cell, the live chart on top. A saved
        # notebook opened untrusted (or on GitHub) strips the iframe and shows the picture.
        return (
            '<div style="display:grid">'
            f'<div style="grid-area:1/1"><img alt="{html.escape(self.title)}" src="{picture}" '
            'style="max-width:100%"></div>'
            f'<div style="grid-area:1/1;background:{self.theme.page}">{frame}</div></div>'
        )

    def _picture(self) -> str | None:
        """The still picture as a data URI, or None when dukpy is missing or drawing fails."""
        from tabsight.render import picture

        if not picture.available():
            return None
        try:
            svg = picture.figure_svg(self.to_dict())
        except Exception:  # the live chart still shows; the picture is a bonus
            return None
        return picture.data_uri(svg) if len(svg) <= PICTURE_MAX_BYTES else None

    def to_svg(self, path: str | Path | None = None, *, width: int = 800) -> str:
        """The chart as a still SVG picture (title, chart and notes), drawn without a browser.

        Needs dukpy: ``pip install tabsight[static]``. Writes it to ``path`` if given.
        """
        from tabsight.render.picture import figure_svg

        svg = figure_svg(self.to_dict(), width=width)
        if path is not None:
            Path(path).write_text(svg, encoding="utf-8")
        return svg

    def explain(self) -> str:
        """Every choice tabsight made for this chart, and why, in plain English."""
        what = {"kpi": "KPI card", "table": "table", "multi_line": "multi-line chart",
                "stacked100_bar": "100% stacked bar chart", "hbar": "horizontal bar chart",
                "choropleth": "filled map", "symbol_map": "symbol map"}.get(
            self.kind, self.kind.replace("_", " ") + " chart"
        )  # fmt: skip
        lines = [f"{self.title} ({what})", ""]
        lines += [f"- {d}" for d in self.decisions]
        if self.notes:
            lines += ["", "Notes shown on the chart:"] + [f"- {n}" for n in self.notes]
        if self.insights:
            lines += ["", "Insights shown under the chart:"] + [
                f"- {i['text']}" for i in self.insights
            ]
        return "\n".join(lines)

    def lint(self, *, ignore: Iterable[str] = (), strict: bool = False) -> LintReport:
        """Check this chart against the rules of good chart design. See ``tabsight.lint``."""
        from tabsight.lint import lint

        return lint(self, ignore=ignore, strict=strict)

    def update(self, patch: dict[str, Any]) -> Figure:
        """Return a copy with ``patch`` deep-merged into the ECharts option.

        The escape hatch for anything tabsight doesn't support. Values must be plain JSON.
        ``formatter`` and keys starting with ``$`` are refused: a string formatter would
        put unescaped data into tooltips, which is how XSS happens.
        """
        if self.option is None:
            raise InvalidSpecError(f"{self.kind} figures have no ECharts option to update")
        _check_patch(patch, 0)
        return dataclasses.replace(self, option=_merge(copy.deepcopy(self.option), patch))


def _notes_height(notes: tuple[str, ...]) -> int:
    """Room for the notes under a chart (about 90 characters a line) so the frame never scrolls."""
    return sum(22 * (1 + len(n) // 90) for n in notes)


def _check_patch(value: Any, depth: int) -> None:
    if depth > _MAX_PATCH_DEPTH:
        raise InvalidSpecError("patch is nested too deeply")
    if isinstance(value, dict):
        for key, inner in value.items():
            if not isinstance(key, str):
                raise InvalidSpecError("patch keys must be strings")
            if key.startswith("$") or key == "formatter":
                raise InvalidSpecError(
                    f"patch key {safe_repr(key)} is not allowed; use tabsight's format options instead"
                )
            _check_patch(inner, depth + 1)
    elif isinstance(value, list):
        for inner in value:
            _check_patch(inner, depth + 1)
    elif not (value is None or isinstance(value, bool | int | float | str)):
        raise InvalidSpecError(f"patch values must be plain JSON, not {type(value).__name__}")
    elif isinstance(value, float) and value != value:
        raise InvalidSpecError("patch values must not be NaN")


def _merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        for key, value in patch.items():
            base[key] = _merge(base.get(key), value) if key in base else copy.deepcopy(value)
        return base
    return copy.deepcopy(patch)
