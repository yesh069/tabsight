# One-line dashboards and the command line

## `ts.auto`: a dashboard from the data alone

```python
import tabsight as ts

orders = ts.load("examples/superstore_sample.csv")
dash = ts.auto(orders, "Superstore")
print(dash)
for line in dash.decisions:
    print(line)
```

```text title="Output"
<Dashboard 'Superstore': 10 tiles, filters ['Order_Date', 'Category', 'Region', 'State']>
measures: Sales (currency, sum), Profit (currency, sum), Quantity (count, sum), Discount (percent, mean)
date: Order_Date (KPIs compare with the previous year)
map: State holds places
filters: Order_Date, Category, Region, State
```

```python
# not run
dash.to_html("superstore.html")
```

`ts.auto` reads the [column profile](profiling.md) and follows fixed rules, so the same data always gives the same dashboard:

1. **KPI cards** for up to four measures, money first. When the dates cover more than a year, each card compares with the previous year.
2. **A line over time** of the main measure, by day, month, quarter or year to suit the time span.
3. **A map**, when a column holds countries, regions or cities.
4. **Bars** (or a donut, for a few parts of a total) of the main measure by the categories with a handful of values. A hierarchy's top level comes first (Region before State).
5. **Filters** on the date and the smallest categories, and an **insights** panel.

`dash.decisions` lists what was chosen and why. Every tile is tried before it is added, and the dashboard is checked against the size limit, dropping filters and then tiles until it fits. A table with no measures still works: tiles count rows (as `Records`), and distinct IDs get a KPI.

The result is an ordinary [`Dashboard`](dashboards.md), so you can keep going:

```python
dash.add("scatter", x="Sales", y="Profit", color="Category", w=12)
spec = (
    dash.to_dict()
)  # or dash.save("superstore.json"); reuse with Dashboard.load(...).bind(new_df)
print(len(dash.tiles), "tiles;", len(spec["tiles"]), "in the saved spec")
```

```text title="Output"
11 tiles; 11 in the saved spec
```

Options: `max_tiles=` (default 10), `insights=False`, and `theme=`, `locale=`, `currency=` as for any dashboard.

## The command line

Installing tabsight adds a `tabsight` command (or run `python -m tabsight`):

```bash
tabsight auto sales.csv                      # writes sales.html next to it
tabsight auto sales.csv -o report.html --theme dark --save sales.json
tabsight build sales.json november.csv -o november.html   # the same dashboard, new data
tabsight chart sales.csv bar --x Region --y Sales -o bar.png   # .html, .svg or .png
tabsight serve sales.csv                     # server mode at http://127.0.0.1:8050/
tabsight profile sales.csv                   # what each column is, and why
tabsight check sales.csv                     # data-quality report (exit code 1 on errors)
tabsight clean sales.csv -o clean.csv        # a cleaned copy; the input is never changed
tabsight recommend sales.csv --x Region --y Sales
```

Files are read with [`ts.load`](loading-data.md): CSV, TSV, Excel (`--sheet`), Parquet and JSON. Output goes where `-o` says, or next to the input. tabsight refuses to write over the input file. Errors print one line and exit with code 2.

`tabsight serve` runs a dashboard in [server mode](web-apps.md) with Python's own web server, on this computer only (`127.0.0.1`). The data stays in Python, so large files and every chart kind stay exact. It only answers requests addressed to `127.0.0.1` or `localhost`, so a web page elsewhere can't reach it by pointing a domain at your computer. `--host 0.0.0.0` lets other computers connect and prints a warning, since anyone who can reach the address can see the data. Add the name they will use with `--allow-host my-laptop.local`.

## PNG pictures

```python
# not run
fig = ts.chart(orders, "bar", x="Region", y="Sales")
fig.to_png("bar.png")  # sharp on high-density screens (scale=2)
fig.to_png("small.png", width=600, scale=1)
```

`to_png` draws the same picture as `fig.to_svg()` and turns it into pixels with resvg. It needs neither a browser nor Node.js: `pip install "tabsight[png]"` installs dukpy and resvg-py.
