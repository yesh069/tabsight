// Render a tabsight figure (Figure.to_dict() JSON) to SVG with ECharts server-side rendering.
// Used for README and documentation images. Usage: node figure_svg.cjs <repo root> <in.json> <out.svg> [width] [height]
"use strict";

const fs = require("fs");
const path = require("path");

const [root, input, output, width = "760", height] = process.argv.slice(2);
const statics = path.join(root, "src", "tabsight", "render", "static");
globalThis.echarts = require(path.join(statics, "echarts.min.js"));
require(path.join(statics, "tabsight.js"));

const figure = JSON.parse(fs.readFileSync(input, "utf8"));
const option = globalThis.tabsight.hydrate(figure.option, figure.locales);
option.animation = false;
option.backgroundColor = figure.theme.tile;

const chart = globalThis.echarts.init(null, null, {
  renderer: "svg",
  ssr: true,
  width: parseInt(width, 10),
  height: parseInt(height || String(figure.height), 10),
});
chart.setOption(option);
fs.writeFileSync(output, chart.renderToSVGString());
chart.dispose();
console.log("wrote " + output);
