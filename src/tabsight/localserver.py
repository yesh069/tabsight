"""``tabsight serve``: a server-mode dashboard on this computer, with Python's own HTTP server.

The only module in tabsight that opens a socket, and only when asked: it listens on
127.0.0.1 by default, answers GET / (the page) and POST /data (``DashboardServer.respond``)
and nothing else. No files are served. For a real web app use ``ts.web`` behind your
own login.
"""

from __future__ import annotations

from typing import Any

__all__ = ["make_server", "serve"]


def serve(dash: Any, *, host: str = "127.0.0.1", port: int = 8050, quiet: bool = False) -> None:
    """Serve ``dash`` in server mode with Python's own HTTP server until Ctrl+C.

    For one person on their own computer. In a real web app use ``ts.web.fastapi_router``
    or ``ts.web.flask_blueprint`` behind your own login."""
    httpd = make_server(dash, host=host, port=port, quiet=quiet)
    print(f"tabsight: serving {dash.title!r} at http://{host}:{httpd.server_port}/ (Ctrl+C stops)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def make_server(
    dash: Any, *, host: str = "127.0.0.1", port: int = 8050, quiet: bool = False
) -> Any:
    """The HTTP server behind ``serve`` (not started): GET / is the page, POST /data answers it."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from tabsight.server import MAX_REQUEST_BYTES
    from tabsight.warnings import InvalidSpecError
    from tabsight.web import HEADERS

    server = dash.server("/data")
    page = server.page().encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for k, v in HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            import json

            size = self.headers.get("Content-Length", "")
            if self.path != "/data" or not size.isdigit() or int(size) > MAX_REQUEST_BYTES:
                self._send(400, b'{"error":"bad request"}', "application/json")
                return
            try:
                reply = server.respond(self.rfile.read(int(size)))
            except InvalidSpecError:
                self._send(400, b'{"error":"bad request"}', "application/json")
                return
            body = json.dumps(reply, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self._send(200, body, "application/json")

        def log_message(self, format: str, *args: Any) -> None:
            if not quiet:
                super().log_message(format, *args)

    return ThreadingHTTPServer((host, port), Handler)
