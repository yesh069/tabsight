// Checks that the bundled ECharts build supports every feature the plan relies on.
// Renders each feature server-side (SVG) in Node, so no browser is needed.
// Usage: node tests/js/echarts_features.cjs <repo root>
"use strict";

const fs = require("fs");
const path = require("path");

const root = process.argv[2] || path.resolve(__dirname, "..", "..");
const echarts = require(path.join(root, "src", "tabsight", "render", "static", "echarts.min.js"));
const world = JSON.parse(
  fs.readFileSync(path.join(root, "data-raw", "naturalearth", "ne_110m_admin_0_countries.geojson"), "utf8")
);

const results = [];

function check(name, fn) {
  try {
    const detail = fn();
    results.push({ name, ok: true, detail: detail || "" });
  } catch (err) {
    results.push({ name, ok: false, detail: String(err && err.message ? err.message : err) });
  }
}

function render(option, opts) {
  const chart = echarts.init(null, null, Object.assign({ renderer: "svg", ssr: true, width: 400, height: 300 }, opts));
  chart.setOption(option);
  const svg = chart.renderToSVGString();
  chart.dispose();
  if (!svg.startsWith("<svg")) throw new Error("no SVG output");
  return svg;
}

// Equal Earth projection (Savric, Patterson, Jenny 2018), in degrees -> plane units.
const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796;
const M = Math.sqrt(3) / 2;
function equalEarth([lon, lat]) {
  const l = (lon * Math.PI) / 180, p = (lat * Math.PI) / 180;
  const t = Math.asin(M * Math.sin(p)), t2 = t * t, t6 = t2 * t2 * t2;
  const x = (l * Math.cos(t)) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)));
  const y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2));
  return [x, -y];
}
function equalEarthInverse([x, y]) {
  let t = -y;
  for (let i = 0; i < 12; i++) {
    const t2 = t * t, t6 = t2 * t2 * t2;
    const f = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2)) + y;
    const fp = A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2);
    t -= f / fp;
  }
  const t2 = t * t, t6 = t2 * t2 * t2;
  const lon = (M * x * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2))) / Math.cos(t);
  const lat = Math.asin(Math.sin(t) / M);
  return [(lon * 180) / Math.PI, (lat * 180) / Math.PI];
}

check("version is 6.x", () => {
  if (!String(echarts.version).startsWith("6.")) throw new Error("got " + echarts.version);
  return echarts.version;
});

check("server-side SVG rendering", () => render({ xAxis: { type: "category", data: ["a", "b"] }, yAxis: {}, series: [{ type: "bar", data: [1, 2] }] }) && "ok");

check("registerMap with GeoJSON + custom Equal Earth projection", () => {
  echarts.registerMap("world", world);
  const back = equalEarthInverse(equalEarth([-6.26, 53.35]));
  if (Math.abs(back[0] + 6.26) > 1e-6 || Math.abs(back[1] - 53.35) > 1e-6) throw new Error("inverse projection mismatch " + back);
  const svg = render({
    series: [{
      type: "map", map: "world",
      projection: { project: equalEarth, unproject: equalEarthInverse },
      data: [{ name: "Ireland", value: 5 }, { name: "India", value: 9 }],
    }],
    visualMap: { min: 0, max: 10 },
  });
  if (!svg.includes("<path")) throw new Error("map drew no paths");
  return world.features.length + " countries drawn";
});

check("LTTB sampling on line series", () => {
  const data = Array.from({ length: 5000 }, (_, i) => [i, Math.sin(i / 50)]);
  render({ xAxis: { type: "value" }, yAxis: {}, series: [{ type: "line", sampling: "lttb", showSymbol: false, data }] });
  return "5000 points";
});

check("large mode scatter", () => {
  const data = Array.from({ length: 20000 }, (_, i) => [i % 200, (i * 7) % 113]);
  render({ xAxis: {}, yAxis: {}, series: [{ type: "scatter", large: true, data }] });
  return "20000 points";
});

// The aria label itself is set on the page element, which does not exist in server-side
// rendering, so it is checked in the browser tests (Phase 8). Here we check decal patterns.
check("decal pattern fills (colour is not the only cue)", () => {
  const svg = render({
    aria: { enabled: true, decal: { show: true } },
    xAxis: { type: "category", data: ["a", "b", "c"] }, yAxis: {},
    series: [{ type: "bar", data: [3, 1, 2] }, { type: "bar", data: [1, 2, 3] }],
  });
  if (!svg.includes("<pattern")) throw new Error("no <pattern> in output");
  return "patterns present";
});

check("dynamic theme switching (setTheme)", () => {
  echarts.registerTheme("ts-dark", { backgroundColor: "#1f2329" });
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 200, height: 100 });
  chart.setOption({ xAxis: { type: "category", data: ["a"] }, yAxis: {}, series: [{ type: "bar", data: [1] }] });
  if (typeof chart.setTheme !== "function") throw new Error("setTheme missing");
  chart.setTheme("ts-dark");
  const svg = chart.renderToSVGString();
  chart.dispose();
  if (!svg.toLowerCase().includes("#1f2329")) throw new Error("theme not applied");
  return "ok";
});

const kinds = {
  treemap: { series: [{ type: "treemap", data: [{ name: "A", value: 3, children: [{ name: "A1", value: 3 }] }, { name: "B", value: 2 }] }] },
  sunburst: { series: [{ type: "sunburst", data: [{ name: "A", children: [{ name: "A1", value: 3 }] }, { name: "B", value: 2 }] }] },
  sankey: { series: [{ type: "sankey", data: [{ name: "a" }, { name: "b" }, { name: "c" }], links: [{ source: "a", target: "b", value: 2 }, { source: "b", target: "c", value: 1 }] }] },
  funnel: { series: [{ type: "funnel", data: [{ name: "a", value: 10 }, { name: "b", value: 5 }] }] },
  gauge: { series: [{ type: "gauge", data: [{ value: 42 }] }] },
  boxplot: { xAxis: { type: "category", data: ["a"] }, yAxis: {}, series: [{ type: "boxplot", data: [[1, 2, 3, 4, 5]] }] },
  "calendar heatmap": {
    calendar: { range: "2017" }, visualMap: { min: 0, max: 10, show: false },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data: [["2017-01-05", 4], ["2017-03-09", 8]] }],
  },
  "heatmap (cartesian)": {
    xAxis: { type: "category", data: ["a", "b"] }, yAxis: { type: "category", data: ["x", "y"] },
    visualMap: { min: 0, max: 5, show: false }, series: [{ type: "heatmap", data: [[0, 0, 1], [1, 1, 4]] }],
  },
  "lines (flow map)": {
    geo: { map: "world" },
    series: [{ type: "lines", coordinateSystem: "geo", data: [{ coords: [[-6.26, 53.35], [72.88, 19.08]] }] }],
  },
  "effectScatter / scatter on geo": {
    geo: { map: "world" },
    series: [{ type: "scatter", coordinateSystem: "geo", data: [{ name: "Dublin", value: [-6.26, 53.35, 5] }] }],
  },
  "brush component": {
    brush: { xAxisIndex: 0 }, xAxis: { type: "category", data: ["a", "b"] }, yAxis: {},
    series: [{ type: "bar", data: [1, 2] }],
  },
  "dataZoom slider": {
    dataZoom: [{ type: "slider" }], xAxis: { type: "category", data: ["a", "b"] }, yAxis: {},
    series: [{ type: "bar", data: [1, 2] }],
  },
};
for (const [name, option] of Object.entries(kinds)) {
  check("chart: " + name, () => render(option) && "ok");
}

let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.detail ? "  (" + r.detail + ")" : ""}`);
}
console.log(`${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
