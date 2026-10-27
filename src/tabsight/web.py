"""Charts and dashboards inside web apps: FastAPI, Flask, Streamlit and Dash.

None of these frameworks is a dependency; each helper imports its framework when called.

    app.include_router(ts.web.fastapi_router(dash, "/sales"))   # FastAPI
    app.register_blueprint(ts.web.flask_blueprint(dash, "/sales"))  # Flask
    ts.streamlit(fig)                                           # Streamlit
    layout = ts.web.dash_iframe(fig)                            # Plotly Dash

The FastAPI and Flask helpers serve a dashboard in server mode (``tabsight.server``):
``GET /sales`` is the page and ``POST /sales/data`` answers its filter changes. Put them
behind your app's own login if the data is private.
"""

# No `from __future__ import annotations`: FastAPI reads the handlers' annotations at run time.

from typing import Any

from tabsight.server import MAX_REQUEST_BYTES, DashboardServer
from tabsight.warnings import InvalidSpecError

__all__ = ["dash_iframe", "fastapi_router", "flask_blueprint", "serve_payload", "streamlit"]

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
_BAD = {"error": "bad request"}  # never echo the request back


def serve_payload(obj: Any, request: Any = None) -> dict[str, Any]:
    """Plain JSON for your own page: a Figure's ``to_dict()``, a Dashboard's payload, a
    server-mode answer (``DashboardServer`` plus the request body), or, for a DataFrame,
    the payload of ``ts.auto(df)``. Draw it with ``tabsight.js`` / ``dashboard.js``."""
    import pandas as pd

    from tabsight.dashboard import Dashboard
    from tabsight.figure import Figure

    if isinstance(obj, DashboardServer):
        return obj.payload() if request is None else obj.respond(request)
    if isinstance(obj, Figure):
        return obj.to_dict()
    if isinstance(obj, Dashboard):
        return obj.build()
    if isinstance(obj, pd.DataFrame):
        from tabsight.auto import auto

        return auto(obj).build()
    raise InvalidSpecError(
        "serve_payload takes a Figure, a Dashboard, a DashboardServer or a DataFrame"
    )


def _server(dash: Any, path: str) -> tuple[DashboardServer, str, str]:
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or (path.endswith("/") and path != "/")
    ):
        raise InvalidSpecError("path must start with '/' and not end with one, e.g. '/sales'")
    page = path
    data = path.rstrip("/") + "/data"
    if isinstance(dash, DashboardServer):
        if dash.url != data:
            raise InvalidSpecError(
                f"this server answers {dash.url!r}; build it with dash.server({data!r})"
            )
        return dash, page, data
    return dash.server(data), page, data


def fastapi_router(dash: Any, path: str = "/dashboard", *, cdn: bool = False) -> Any:
    """A FastAPI ``APIRouter`` serving ``dash`` in server mode at ``path``."""
    from fastapi import APIRouter, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from starlette.concurrency import run_in_threadpool

    srv, page_path, data_path = _server(dash, path)
    document = srv.page(cdn=cdn)
    router = APIRouter()

    @router.get(page_path, response_class=HTMLResponse)
    def page() -> HTMLResponse:
        return HTMLResponse(document, headers=HEADERS)

    @router.post(data_path)
    async def data(request: Request) -> JSONResponse:
        size = request.headers.get("content-length")
        if size is not None and (not size.isdigit() or int(size) > MAX_REQUEST_BYTES):
            return JSONResponse(_BAD, status_code=413, headers=HEADERS)
        body = b""
        async for chunk in request.stream():  # stop reading as soon as it is too large
            body += chunk
            if len(body) > MAX_REQUEST_BYTES:
                return JSONResponse(_BAD, status_code=413, headers=HEADERS)
        try:
            reply = await run_in_threadpool(srv.respond, body)  # pandas work off the event loop
        except InvalidSpecError:  # BadRequest, or an answer over the size limit
            return JSONResponse(_BAD, status_code=400, headers=HEADERS)
        return JSONResponse(reply, headers=HEADERS)

    return router


def flask_blueprint(
    dash: Any, path: str = "/dashboard", *, name: str = "tabsight", cdn: bool = False
) -> Any:
    """A Flask ``Blueprint`` serving ``dash`` in server mode at ``path``."""
    from flask import Blueprint, Response, jsonify, request

    srv, page_path, data_path = _server(dash, path)
    document = srv.page(cdn=cdn)
    bp = Blueprint(name, __name__)

    def page() -> Response:
        return Response(document, mimetype="text/html", headers=HEADERS)

    def data() -> Any:
        if request.content_length is None:
            return jsonify(_BAD), 411, HEADERS
        if request.content_length > MAX_REQUEST_BYTES:
            return jsonify(_BAD), 413, HEADERS
        try:
            reply = srv.respond(request.get_data(cache=False))
        except InvalidSpecError:  # BadRequest, or an answer over the size limit
            return jsonify(_BAD), 400, HEADERS
        return jsonify(reply), 200, HEADERS

    bp.add_url_rule(page_path, f"{name}_page", page, methods=["GET"])
    bp.add_url_rule(data_path, f"{name}_data", data, methods=["POST"])
    return bp


def _height(obj: Any) -> int:
    from tabsight.dashboard import Dashboard

    if isinstance(obj, Dashboard):
        rows, width = 1, 0
        for _, w in obj.build_layout():
            if width + w > 12:
                rows, width = rows + 1, 0
            width += w
        return 220 + 470 * rows
    return int(getattr(obj, "height", 420)) + 140


def _document(obj: Any, cdn: bool) -> str:
    from tabsight.dashboard import Dashboard
    from tabsight.figure import Figure

    if not isinstance(obj, Figure | Dashboard):
        raise InvalidSpecError("pass a Figure (ts.chart) or a Dashboard")
    return obj.to_html(cdn=cdn)


def streamlit(obj: Any, *, height: int | None = None, cdn: bool = False) -> Any:
    """Show a Figure or Dashboard in a Streamlit app (in its own sandboxed frame)."""
    import streamlit.components.v1 as components

    return components.html(_document(obj, cdn), height=height or _height(obj), scrolling=True)


def dash_iframe(obj: Any, *, height: int | None = None, cdn: bool = False, **props: Any) -> Any:
    """A Plotly Dash ``html.Iframe`` showing a Figure or Dashboard (scripts only, no
    access to the host page)."""
    from dash import html

    style = {"width": "100%", "height": f"{height or _height(obj)}px", "border": "0"}
    return html.Iframe(
        srcDoc=_document(obj, cdn), sandbox="allow-scripts allow-downloads", style=style, **props
    )
