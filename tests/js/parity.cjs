// Formats every case from a Python-generated file with tabsight.js and reports
// any output that differs from Python's. Usage: node parity.cjs <runtime.js> <cases.json>
"use strict";

const fs = require("fs");

require(process.argv[2]);
const tabsight = globalThis.tabsight;
const data = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

let failures = 0;
for (const c of data.cases) {
  let got;
  try {
    got = tabsight.formatNumber(c.value, c.spec, data.locales);
  } catch (err) {
    got = "ERROR: " + err.message;
  }
  if (got !== c.expected) {
    failures++;
    if (failures <= 25) {
      console.log(JSON.stringify({ value: c.value, spec: c.spec, expected: c.expected, got }));
    }
  }
}
console.log(`${data.cases.length - failures}/${data.cases.length} match`);
process.exit(failures ? 1 : 0);
