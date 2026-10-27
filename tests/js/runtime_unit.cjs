// Unit checks for tabsight.js that need no browser: tooltip escaping and hydration.
// Usage: node runtime_unit.cjs <runtime.js>
"use strict";

const assert = require("assert");

require(process.argv[2]);
const ts = globalThis.tabsight;

const locales = {
  en_US: {
    decimal: ".", group: ",", grouping: [3], currency_before: true, currency_space: false,
    percent_space: false, compact: [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]], compact_space: false,
  },
};
const spec = {
  unit: "currency", style: "full", locale: "en_US", decimals: null, percent_scale: "fraction",
  duration_unit: "seconds", negative: "minus", sign: false, currency_symbol: "$", zero_decimal: false,
};
const evil = '<img src=x onerror=alert(1)>"\'&';

// escapeHtml
assert.strictEqual(ts.escapeHtml(evil), "&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;");
assert.strictEqual(ts.escapeHtml(null), "");

// Hydration turns {"$fmt"} into a function and leaves plain data alone.
const option = ts.hydrate(
  {
    title: { text: evil },
    yAxis: { axisLabel: { formatter: { $fmt: { ...spec, style: "compact" } } } },
    tooltip: { formatter: { $tooltip: { trigger: "axis", fmt: spec, series_fmt: {} } } },
    pie: { formatter: { $tooltip: { trigger: "item", fmt: spec, percent: true,
      percent_fmt: { ...spec, unit: "percent", percent_scale: "whole" } } } },
  },
  locales
);
assert.strictEqual(option.title.text, evil); // data stays data (ECharts draws titles as canvas text)
assert.strictEqual(typeof option.yAxis.axisLabel.formatter, "function");
assert.strictEqual(option.yAxis.axisLabel.formatter(2297200.86), "$2.3M");

// Axis tooltip: every data-derived string is escaped, colours are re-validated.
const axisHtml = option.tooltip.formatter([
  { axisValueLabel: evil, seriesName: evil, value: 1234.5, color: "#4e79a7" },
  { axisValueLabel: evil, seriesName: "b", value: 2, color: "red;background:url(javascript:alert(1))" },
  { axisValueLabel: evil, seriesName: "skipped", value: null, color: "#000" },
]);
assert.ok(!axisHtml.includes("<img"), "raw markup in axis tooltip");
assert.ok(axisHtml.includes("&lt;img src=x onerror=alert(1)&gt;"));
assert.ok(axisHtml.includes("$1,235"));
assert.ok(!axisHtml.includes("javascript:"), "unsafe colour reached the tooltip");
assert.ok(!axisHtml.includes("skipped"), "missing values should be left out");

// Item tooltip (donut) with a share.
const itemHtml = option.pie.formatter({ name: evil, value: 10, color: "#f28e2b", percent: 12.34 });
assert.ok(!itemHtml.includes("<img"));
assert.ok(itemHtml.includes("12.3%"));

// The runtime contains no eval-like constructs.
const source = require("fs").readFileSync(process.argv[2], "utf8");
for (const banned of ["eval(", "new Function", "innerHTML", "document.write", "setTimeout(\"", "fetch(", "XMLHttpRequest"]) {
  assert.ok(!source.includes(banned), "runtime must not use " + banned);
}

console.log("all runtime checks passed");
