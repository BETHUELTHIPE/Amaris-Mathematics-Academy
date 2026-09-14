import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const reportDir = path.resolve(process.env.LIGHTHOUSE_REPORT_DIR ?? ".lighthouseci");
const target = Number(process.env.LIGHTHOUSE_PERFORMANCE_TARGET ?? "1");

async function collectJsonFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await collectJsonFiles(fullPath)));
    else if (entry.isFile() && entry.name.endsWith(".json")) files.push(fullPath);
  }
  return files;
}

function metric(report, auditId) {
  const audit = report.audits?.[auditId];
  if (!audit) return "n/a";
  if (audit.displayValue) return audit.displayValue;
  if (typeof audit.numericValue === "number") return Math.round(audit.numericValue).toString();
  return "n/a";
}

let files;
try {
  files = await collectJsonFiles(reportDir);
} catch (error) {
  console.error(`Lighthouse report directory is unavailable: ${error.message}`);
  process.exit(1);
}

const reports = [];
for (const file of files) {
  try {
    const parsed = JSON.parse(await readFile(file, "utf8"));
    if (parsed?.categories?.performance && parsed?.finalDisplayedUrl) reports.push(parsed);
  } catch {
    // Ignore non-Lighthouse JSON files such as manifests and metadata.
  }
}

if (reports.length === 0) {
  console.error(`No Lighthouse LHR JSON reports found under ${reportDir}.`);
  process.exit(1);
}

reports.sort((a, b) => a.finalDisplayedUrl.localeCompare(b.finalDisplayedUrl));

console.log("\nLighthouse performance report");
console.log("URL | Performance | FCP | LCP | Speed Index | TBT | CLS");
console.log("--- | ---: | ---: | ---: | ---: | ---: | ---:");

let failed = false;
for (const report of reports) {
  const score = report.categories.performance.score ?? 0;
  const score100 = Math.round(score * 100);
  console.log(
    `${report.finalDisplayedUrl} | ${score100}/100 | ${metric(report, "first-contentful-paint")} | ${metric(report, "largest-contentful-paint")} | ${metric(report, "speed-index")} | ${metric(report, "total-blocking-time")} | ${metric(report, "cumulative-layout-shift")}`,
  );
  if (score + Number.EPSILON < target) failed = true;
}

const minimum = Math.min(...reports.map((report) => report.categories.performance.score ?? 0));
console.log(`\nMinimum performance score: ${Math.round(minimum * 100)}/100`);
console.log(`Required performance score: ${Math.round(target * 100)}/100`);

if (failed) {
  console.error("One or more measured pages are below the required Lighthouse performance target.");
  process.exit(1);
}
