"""Server mode (PLAN 9.3): the data stays in Python; the page asks for numbers.

An offline dashboard carries one shared table and filters it in the browser. That table
has a size limit, and medians and distinct counts need every value. In server mode the
page carries no rows. Each time the viewer filters, it posts its filters to your app and
gets back, for each tile on screen:

- a small table grouped by just what that tile needs, from the rows that pass the
  filters (the page draws it with the same code as offline, so clicks, drill-down,
  comparisons and refitted trends behave the same), or
- for tiles the browser can't recompute (scatter plots of raw rows, histograms...), the
  finished chart, drawn in Python from the filtered rows. So in server mode every tile
  follows the filters.

The request comes from the browser, so it is untrusted: its size is capped, its shape is
checked, and filters keep only known columns and known values (the same rule the page
uses for the address bar). Nothing in it reaches ``eval``, a query string or a file path.

    server = dash.server("/sales/data")
    html = server.page()                  # serve at GET /sales
    reply = server.respond(request_body)  # serve at POST /sales/data, as JSON

``ts.web.fastapi_router`` and ``ts.web.flask_blueprint`` wire both up for you. Who may
see the dashboard (logins, permissions) is your app's job.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import pandas as pd

from tabsight.aggregate import _part_name
from tabsight.theme import get_theme
from tabsight.warnings import InvalidSpecError

if TYPE_CHECKING:
    from tabsight.dashboard import Dashboard, _SharedTable

__all__ = ["MAX_REQUEST_BYTES", "DashboardServer"]

MAX_REQUEST_BYTES = 256_000
MAX_RESPONSE_MB = 20.0  # per tile
MAX_VALUES = 5000  # values in one "in" filter
# A path on this site (not "//host", which browsers read as another site) or an http(s) address.
_URL_RE = re.compile(r"(/(?!/)[\w\-./~%]*|https?://[\w.\-]+(:\d{1,5})?(/[\w\-./~%]*)?)")
_PARTS = ("sum", "count", "min", "max", "values", "wsum", "wtotal")


class BadRequest(InvalidSpecError):
    """The request from the page is not one tabsight would send."""


def _strings(value: Any, out: set[str], depth: int = 0) -> set[str]:
    """Every string in a binding: the table columns and parts it reads."""
    if depth > 30:
        return out
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, Mapping):
        for k, v in value.items():
            out.add(str(k))
            _strings(v, out, depth + 1)
    elif isinstance(value, list | tuple):
        for v in value:
            _strings(v, out, depth + 1)
    return out


class DashboardServer:
    """Answers a server-mode dashboard page. Build it with ``dash.server(url)``."""

    def __init__(self, dash: Dashboard, url: str) -> None:
        if not isinstance(url, str) or len(url) > 500 or not _URL_RE.fullmatch(url):
            raise InvalidSpecError(
                "url must be a path such as '/dashboard/data' or an http(s) address"
            )
        self.url = url
        self.tiles = copy.deepcopy(dash.tiles)
        self.theme = dash.theme
        self._built = dash._build(server=True)
        self._payload = self._built.payload
        self._payload["server"] = {"url": url}
        self._ids = {t["id"]: i for i, t in enumerate(self._payload["tiles"])}
        self._known: dict[str, set[str | None]] = {}

    # ------------------------------------------------------------ what the app serves

    def payload(self) -> dict[str, Any]:
        """The page payload (no rows), for your own page that loads ``dashboard.js``."""
        return copy.deepcopy(self._payload)

    def page(self, *, cdn: bool = False) -> str:
        """The dashboard page. It may only talk to ``url`` (its Content Security Policy says so)."""
        from tabsight.render.dashboard_html import dashboard_page
        from tabsight.settings import resolve

        theme = get_theme(self.theme or resolve().theme)
        return dashboard_page(self._payload, theme, cdn=cdn, connect=self.url)

    def respond(self, body: bytes | str | Mapping[str, Any]) -> dict[str, Any]:
        """Answer one request from the page (JSON in, JSON-ready dict out).

        Raises :class:`BadRequest` (a ``ValueError``) when the request is malformed; reply
        400 then."""
        req = self._parse(body)
        state = self.sanitize(req.get("state"))
        asked = req.get("tiles", [])
        if not isinstance(asked, list) or len(asked) > len(self._ids):
            raise BadRequest("tiles must be a list of the page's tiles")
        out: dict[str, Any] = {"tiles": {}}
        for item in asked:
            if not isinstance(item, Mapping) or item.get("id") not in self._ids:
                raise BadRequest("unknown tile")
            out["tiles"][item["id"]] = self._tile(item, state)
        if req.get("insights") is True and self._payload.get("live_insights"):
            out["insights"] = self._insights(state)
        return out

    # ------------------------------------------------------------ checking the request

    def _parse(self, body: bytes | str | Mapping[str, Any]) -> Mapping[str, Any]:
        if isinstance(body, Mapping):
            req: Any = body
        else:
            raw = body.encode("utf-8") if isinstance(body, str) else body
            if not isinstance(raw, bytes | bytearray) or len(raw) > MAX_REQUEST_BYTES:
                raise BadRequest("request too large")
            try:
                req = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as e:
                raise BadRequest("request is not JSON") from e
        if not isinstance(req, Mapping):
            raise BadRequest("request must be a JSON object")
        return req

    def _values(self, col: str) -> set[str | None] | None:
        if col not in self._known:
            for table in self._built.tables.values():
                if col in table.dims:
                    self._known[col] = set(table.dims[col].unique().tolist())
                    break
            else:
                return None
        return self._known[col]

    def sanitize(self, raw: Any) -> dict[str, dict[str, Any]]:
        """Keep only filters on known columns with known values (as the page does)."""
        out: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, Mapping):
            return out
        for col, f in list(raw.items())[:100]:
            if not isinstance(col, str) or col.startswith("__") or not isinstance(f, Mapping):
                continue
            known = self._values(col)
            if known is None:
                continue
            source = f.get("source") if f.get("source") in self._ids else None
            mode = "highlight" if f.get("mode") == "highlight" else "filter"
            lo, hi = f.get("lo"), f.get("hi")
            if f.get("type") == "range":
                if isinstance(lo, str) and isinstance(hi, str) and lo in known and hi in known:
                    out[col] = {
                        "type": "range",
                        "lo": lo,
                        "hi": hi,
                        "source": source,
                        "mode": "filter",
                    }
            elif f.get("type") == "in" and isinstance(f.get("values"), list):
                kept = [
                    v
                    for v in f["values"][:MAX_VALUES]
                    if (v is None or isinstance(v, str)) and v in known
                ]
                if kept:
                    out[col] = {"type": "in", "values": kept, "source": source, "mode": mode}
        return out

    # ------------------------------------------------------------ answering

    def _rows(
        self, table: _SharedTable, state: Mapping[str, Mapping[str, Any]], keep: set[str]
    ) -> pd.Series:
        """Rows passing every filter except those in ``keep`` (the page applies those itself)."""
        rows = pd.Series(True, index=table.frame.index)
        for col, f in state.items():
            if col in keep or col not in table.dims or f["mode"] == "highlight":
                continue
            keys = table.dims[col]
            if f["type"] == "range":
                text = keys.astype("string")
                rows &= (text >= f["lo"]).fillna(False) & (text <= f["hi"]).fillna(False)
            else:
                values = [v for v in f["values"] if v is not None]
                hit = keys.isin(values)
                if None in f["values"]:
                    hit |= keys.isna()
                rows &= hit
        return rows

    def _table(self, table: _SharedTable, refs: set[str], extra: Sequence[str], state: Mapping[str, Any],
               keep: set[str]) -> dict[str, Any]:  # fmt: skip
        dims = [c for c in table.dims if c in refs or c in extra or c in keep]
        measures = [
            i for i in range(len(table.measures)) if any(_part_name(i, p) in refs for p in _PARTS)
        ]
        return table.encode(rows=self._rows(table, state, keep), dims=dims, measures=measures,
                            max_mb=MAX_RESPONSE_MB)  # fmt: skip

    def _tile(
        self, item: Mapping[str, Any], state: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        tid = item["id"]
        i = self._ids[tid]
        tile = self._payload["tiles"][i]
        view = item.get("view", 0)
        if type(view) is not int or not 0 <= view < len(tile["views"]):
            raise BadRequest("unknown view")
        theme = item.get("theme")
        sides = tile["views"][view]["themes"]
        side = sides.get(theme) if isinstance(theme, str) else None
        if side is None:
            theme, side = next(iter(sides.items()))
        theme = str(theme)
        table = self._built.tables[tile["data"]]
        drill = item.get("drill", [])
        if (
            not isinstance(drill, list)
            or len(drill) > 5
            or not all(isinstance(c, str) and c in table.dims for c in drill)
        ):
            raise BadRequest("unknown drill-down column")
        if "binding" in side:
            refs = _strings(side["binding"], set())
            # Filters the page must apply itself: highlights, the tile's own selection, and date
            # ranges the tile reads (a KPI compares them with the same months a year earlier).
            # Every other filter is applied here, so the table holds only the matching rows.
            keep = {c for c, f in state.items() if f["mode"] == "highlight" or f["source"] == tid
                    or (f["type"] == "range" and c in refs)}  # fmt: skip
            return {"table": self._table(table, refs, drill, state, keep)}
        # A tile the page can't recompute: draw it here from the filtered rows.
        rows = self._rows(table, state, set())
        frame = self._built.frames[tile["data"]][rows]
        if frame.empty:
            return {"empty": True}
        args = {**self.tiles[i], **self._built.view_args.get((i, tile["views"][view]["id"]), {})}
        try:
            fig = self._built.draw(args, self._built.colors, get_theme(theme), frame=frame)
        except InvalidSpecError:
            return {"empty": True}
        figure = fig.to_dict()
        figure.pop("maps", None)  # the page registered every shape when it opened
        return {"figure": figure}

    def _insights(self, state: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        refs = _strings(self._payload["live_insights"], set())
        table = self._built.tables["main"]
        keep = {
            c
            for c, f in state.items()
            if f["mode"] == "highlight" or (f["type"] == "range" and c in refs)
        }
        return self._table(table, refs, (), state, keep)
