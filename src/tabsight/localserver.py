"""``tabsight serve``: a server-mode dashboard on this computer, with Python's own HTTP server.

The only module in tabsight that opens a socket, and only when asked: it listens on
127.0.0.1 by default, answers GET / (the page) and POST /data (``DashboardServer.respond``)
and nothing else. No files are served. For a real web app use ``ts.web`` behind your
own login.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = ["make_server", "serve"]


LOOPBACK = ("127.0.0.1", "localhost", "[::1]")
WILDCARD = ("0.0.0.0", "::", "")  # noqa: S104 - listed so they are never accepted as a Host name


def serve(dash: Any, *, host: str = "127.0.0.1", port: int = 8050, quiet: bool = False,
          allow_hosts: Sequence[str] = ()) -> None:  # fmt: skip
    """Serve ``dash`` in server mode with Python's own HTTP server until Ctrl+C.

    For one person on their own computer. In a real web app use ``ts.web.fastapi_router``
    or ``ts.web.flask_blueprint`` behind your own login."""
    httpd = make_server(dash, host=host, port=port, quiet=quiet, allow_hosts=allow_hosts)
    print(f"tabsight: serving {dash.title!r} at http://{host}:{httpd.server_port}/ (Ctrl+C stops)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def make_server(dash: Any, *, host: str = "127.0.0.1", port: int = 8050, quiet: bool = False,
                allow_hosts: Sequence[str] = ()) -> Any:  # fmt: skip
    """The HTTP server behind ``serve`` (not started): GET / is the page, POST /data answers it.

    Only requests addressed to this computer's loopback names, ``host`` itself or one of
    ``allow_hosts`` are answered. A web page elsewhere can point its own domain at
    127.0.0.1 ("DNS rebinding"); its requests still carry its own name, so they are refused.
    POST requests must be ``application/json``, which a browser won't send to another
    site without asking it first (and this server never agrees)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from tabsight.server import MAX_REQUEST_BYTES
    from tabsight.warnings import InvalidSpecError
    from tabsight.web import HEADERS

    server = dash.server("/data")
    page = server.page().encode("utf-8")

    names = {n.lower() for n in (*LOOPBACK, host, *allow_hosts) if n and n not in WILDCARD}

    class Handler(BaseHTTPRequestHandler):
        def _allowed(self) -> bool:
            given = (self.headers.get("Host") or "").strip().lower()
            name, _, given_port = (
                given.rpartition(":") if not given.endswith("]") else (given, "", "")
            )
            if given_port and given_port != str(getattr(self.server, "server_port", "")):
                return False
            return (name or given) in names

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for k, v in HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not self._allowed():
                self._send(421, b"wrong host", "text/plain; charset=utf-8")
                return
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            import json

            if not self._allowed():
                self._send(421, b'{"error":"wrong host"}', "application/json")
                return
            size = self.headers.get("Content-Length", "")
            kind = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if (
                self.path != "/data"
                or kind != "application/json"
                or not size.isdigit()
                or int(size) > MAX_REQUEST_BYTES
            ):
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
