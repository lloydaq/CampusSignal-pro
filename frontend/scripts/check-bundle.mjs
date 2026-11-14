// NFR-PERF-002 (Phase 9d): the JavaScript a first visit downloads, gzipped, must stay within
// 250 KB. That's the entry script in dist/index.html plus the chunks it imports statically
// (modulepreload links). Run after `npm run build`.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const BUDGET_KB = 250;
const html = readFileSync("dist/index.html", "utf8");
const files = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
if (files.length === 0) throw new Error("No scripts found in dist/index.html: build first.");
let total = 0;
for (const file of files) {
  const size = gzipSync(readFileSync(`dist/${file}`)).length / 1024;
  total += size;
  console.log(`${file}  ${size.toFixed(1)} KB gzipped`);
}
console.log(`initial JavaScript: ${total.toFixed(1)} KB gzipped (budget ${BUDGET_KB} KB)`);
if (total > BUDGET_KB) {
  console.error("Over the NFR-PERF-002 budget: split more routes or drop a dependency.");
  process.exit(1);
}
