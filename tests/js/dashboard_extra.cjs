// Dashboard checks beyond chart data: trend lines and forecasts redrawn after filtering,
// insights recomputed after filtering, and tiles with their own dataset.
// Usage: node dashboard_extra.cjs <tabsight.js> <dashboard.js> <cases.json>
"use strict";

const fs = require("fs");

require(process.argv[2]);
require(process.argv[3]);
const D = globalThis.tabsightDashboard;
const cases = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const payload = cases.payload;
const table = new D.Table(cases.dataset ? payload.datasets[cases.dataset] : payload.data);

function itemValue(d) {
  return d && typeof d === "object" && !Array.isArray(d) ? d.value : d;
}

let out;
if (cases.mode === "insights") {
  out = cases.filters.map((f) => D.computeInsights(payload, table, D.prepare(f)).map((i) => ({ kind: i.kind, text: i.text })));
} else if (cases.mode === "series") {
  out = cases.filters.map((f) => {
    const prepared = D.prepare(f);
    return payload.tiles.map((t) => {
      const flat = D.flatTile({ tile: t, view: 0 }, payload.theme.name);
      const opt = D.compute(payload, table, flat, prepared).figure.option;
      return opt.series.map((x) => ({
        name: x.name,
        data: x.data.map(itemValue),
        refs: x.markLine ? x.markLine.data.map((d) => d.yAxis) : null,
        points: x.markPoint ? x.markPoint.data.map((d) => d.coord) : null,
      }));
    });
  });
} else if (cases.mode === "tile") {
  const tile = payload.tiles[cases.tile];
  const flat = D.flatTile({ tile: tile, view: 0 }, payload.theme.name);
  const opt = D.compute(payload, table, flat, D.prepare(cases.filters[0])).figure.option;
  out = { labels: opt.xAxis.data, values: opt.series[0].data.map(itemValue) };
}
process.stdout.write(JSON.stringify(out));
