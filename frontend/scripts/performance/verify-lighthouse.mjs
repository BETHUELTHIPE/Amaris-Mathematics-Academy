import { readFile } from "node:fs/promises";

const files = process.argv.slice(2);
if (!files.length) throw new Error("At least one Lighthouse JSON report is required.");

const limits = {
  performance: 0.85,
  accessibility: 0.95,
  "best-practices": 0.9,
  seo: 0.9,
  "first-contentful-paint": 2000,
  "largest-contentful-paint": 2500,
  "cumulative-layout-shift": 0.1,
  "total-blocking-time": 200,
  "speed-index": 3000,
};

let failed = false;
for (const file of files) {
  const report = JSON.parse(await readFile(file, "utf8"));
  const url = report.finalDisplayedUrl ?? report.finalUrl ?? file;
  const categoryChecks = ["performance", "accessibility", "best-practices", "seo"];
  for (const key of categoryChecks) {
    const observed = report.categories?.[key]?.score ?? 0;
    const minimum = limits[key];
    if (observed < minimum) {
      failed = true;
      console.error(`Lighthouse FAIL ${url}: ${key} ${(observed * 100).toFixed(0)} < ${minimum * 100}`);
    }
  }

  const auditChecks = [
    "first-contentful-paint",
    "largest-contentful-paint",
    "cumulative-layout-shift",
    "total-blocking-time",
    "speed-index",
  ];
  for (const key of auditChecks) {
    const observed = report.audits?.[key]?.numericValue;
    const maximum = limits[key];
    if (typeof observed !== "number" || observed > maximum) {
      failed = true;
      console.error(`Lighthouse FAIL ${url}: ${key} ${observed ?? "missing"} > ${maximum}`);
    }
  }

  if (!failed) console.log(`Lighthouse PASS ${url}`);
}

if (failed) process.exit(1);
