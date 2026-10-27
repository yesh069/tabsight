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

// Everything a chart draws from data: category axes, series data and links, colour scales.
function extract(opt) {
  const axes = [];
  for (const key of ["xAxis", "yAxis"]) {
    const list = Array.isArray(opt[key]) ? opt[key] : opt[key] ? [opt[key]] : [];
    list.forEach((a) => a.type === "category" && axes.push(a.data));
  }
  const sortOutliers = (s) => (s.name === "Outliers" ? s.data.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]) : s.data);
  const series = (opt.series || []).map((s) => ({ type: s.type, name: s.name ?? null, data: s.data ? sortOutliers(s) : null, links: s.links ?? null, max: s.max ?? null }));
  const vm = opt.visualMap ? [opt.visualMap.min, opt.visualMap.max] : null;
  const cal = opt.calendar ? (Array.isArray(opt.calendar) ? opt.calendar : [opt.calendar]).map((c) => c.range) : null;
  return { axes, series, vm, cal };
}

function summary(tile, result) {
  const fig = result.figure;
  if (cases.deep && cases.deep.includes(tile.id)) return { deep: extract(fig.option) };
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

// Server mode: cases.tables[k][tileId] is the small table the server sent for filter case k.
const tableFor = (k, id) => (cases.tables ? new D.Table(cases.tables[k][id]) : table);
const out = cases.filters.map((filters, k) => {
  const prepared = D.prepare(filters);
  return payload.tiles
    .map((t) => D.flatTile({ tile: t, view: 0 }, payload.theme.name))
    .filter((t) => t.binding)
    .map((t) => ({ id: t.id, ...summary(t, D.compute(payload, tableFor(k, t.id), t, prepared)) }));
});
const sanitized = (cases.sanitize || []).map((raw) => D.sanitize(raw, table, payload));
process.stdout.write(JSON.stringify(cases.sanitize ? { results: out, sanitized } : out));
