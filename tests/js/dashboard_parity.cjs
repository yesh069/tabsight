// Recompute dashboard tiles under given filters, as the browser would, and print the
// results as JSON so tests/test_dashboard.py can compare them with Python.
// Usage: node dashboard_parity.cjs <tabsight.js> <dashboard.js> <cases.json>
"use strict";

const fs = require("fs");

require(process.argv[2]);
require(process.argv[3]);
const D = globalThis.tabsightDashboard;
const cases = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const payload = cases.payload;
const table = new D.Table(payload.data);

function itemValue(v) {
  if (v && typeof v === "object" && !Array.isArray(v)) return v.value === undefined ? null : v.value;
  return v === undefined ? null : v;
}

function summary(tile, result) {
  const fig = result.figure;
  if (fig.kind === "kpi") return { kpi: fig.kpi };
  if (fig.kind === "table") return { rows: fig.table.rows };
  const opt = fig.option;
  if (fig.kind === "choropleth") {
    const out = {};
    opt.series[0].data.forEach((d) => (out[d.name] = d.value));
    return { map: out };
  }
  if (fig.kind === "donut") {
    return { labels: opt.series[0].data.map((d) => d.name), series: { [tile.binding.measures[0].label]: opt.series[0].data.map((d) => d.value) } };
  }
  const cat = tile.binding.horizontal ? opt.yAxis : opt.xAxis;
  const series = {};
  opt.series.forEach((s) => (series[s.name] = s.data.map(itemValue)));
  return { labels: cat.data, series };
}

const out = cases.filters.map((filters) => {
  const prepared = D.prepare(filters);
  return payload.tiles
    .filter((t) => t.binding)
    .map((t) => ({ id: t.id, ...summary(t, D.compute(payload, table, t, prepared)) }));
});
const sanitized = (cases.sanitize || []).map((raw) => D.sanitize(raw, table, payload));
process.stdout.write(JSON.stringify(cases.sanitize ? { results: out, sanitized } : out));
