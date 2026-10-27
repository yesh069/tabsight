# Web apps and server mode

## Two ways to serve a dashboard

| | Offline file (`dash.to_html()`) | Server mode (`dash.server(url)`) |
|---|---|---|
| Where the data lives | In the page, as one pre-aggregated table | In Python; the page holds no rows |
| Size limit | 5 MB by default (`max_size_mb`) | None for the page; each answer is small |
| After a filter | The browser recomputes | The page asks your app, then draws the answer |
| Scatter plots of rows, histograms... | Drawn from all the data ("Not affected by filters") | Redrawn from the filtered rows |
| Needs | Nothing: open the file | A running Python web app |

In server mode the page posts its filters to your app. For each tile on screen, it gets back a small table grouped by just what that tile needs, built from the rows that pass the filters. The page then draws it with the same code as the offline file, so clicks, drill-down, comparisons and trend lines behave the same. Tiles the browser can't recompute come back as finished charts drawn in Python.

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
dash = ts.Dashboard("Sales", data=orders, filters=["Region"]).add("bar", x="Region", y="Sales")
server = dash.server("/sales/data")

reply = server.respond(
    {"state": {"Region": {"type": "in", "values": ["West"]}}, "tiles": [{"id": "t0", "view": 0}]}
)
table = reply["tiles"]["t0"]["table"]
print(table["rows"], "row(s):", table["dims"]["Region"]["values"])
```

```text title="Output"
1 row(s): ['West']
```

`server.page()` is the HTML to serve, and `server.respond(body)` answers the page's requests. The helpers below wire both up.

## FastAPI

```py
from fastapi import FastAPI
import tabsight as ts

app = FastAPI()
app.include_router(ts.web.fastapi_router(dash, "/sales"))
# GET /sales is the page; POST /sales/data answers it
```

## Flask

```py
from flask import Flask
import tabsight as ts

app = Flask(__name__)
app.register_blueprint(ts.web.flask_blueprint(dash, "/sales"))
```

`pip install "tabsight[web]"` installs FastAPI and Flask. You only need the one you use.

## Streamlit and Dash

```py
ts.streamlit(fig)  # a Figure or a Dashboard, in a Streamlit app
layout = html.Div([ts.web.dash_iframe(dash)])  # Plotly Dash
```

Both show the offline page in a sandboxed frame (scripts only, no access to the host page).

## Your own page

`ts.serve_payload(obj)` returns plain JSON. It accepts a Figure (`fig.to_dict()`), a Dashboard (its payload), a `DashboardServer` (its payload, or its answer when you pass a request body) or a DataFrame (the payload of `ts.auto(df)`). Draw it with `tabsight.js` and `dashboard.js` (`ts.runtime_js()`).

## Security

- **Requests are untrusted.** Bodies over 256 KB are refused. The shape of each request is checked. Filters keep only known columns and known values, the same rule the page applies to the address bar. Malformed requests get `400 {"error": "bad request"}`, and nothing is echoed back.
- **Only JSON is accepted.** Data requests must be `application/json`, or the response is 415. A web page on another site can't send that without asking first (a CORS preflight these routes never approve).
- **Check the host name too.** If your app runs on `localhost`, a hostile site can point its own domain at 127.0.0.1 ("DNS rebinding") and read the answers. Allow only your real host names: `TrustedHostMiddleware` in FastAPI/Starlette, `TRUSTED_HOSTS` in Flask 3.1+. `tabsight serve` does this for you.
- **The page may only talk to its own address.** Its Content Security Policy adds `connect-src` for that one origin. Offline pages send nothing anywhere.
- **Who may see the data is your app's job.** Put the routes behind your own login. tabsight adds `nosniff`, `no-referrer` and `no-store` headers.
- The pandas work runs in a worker thread under FastAPI, so it doesn't block other requests.
