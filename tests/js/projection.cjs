// Map projections in tabsight.js: values for Python to compare with its own formulas, and
// a check that unproject(project(p)) gives p back.
// Usage: node projection.cjs <runtime.js> <points.json>   (prints JSON)
"use strict";

const assert = require("assert");
const fs = require("fs");

require(process.argv[2]);
const ts = globalThis.tabsight;
const points = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = {};
for (const name of ["equal_earth", "mercator", "natural"]) {
  const proj = ts.hydrate({ $projection: name }, {});
  out[name] = points.map((p) => {
    const xy = proj.project(p);
    const back = proj.unproject(xy);
    assert.ok(Math.abs(back[0] - p[0]) < 1e-6 && Math.abs(back[1] - p[1]) < 1e-6, `${name} round trip at ${p}`);
    return xy;
  });
}
console.log(JSON.stringify(out));
