import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const [profile, ...files] = process.argv.slice(2);
if (!profile || !["perfect", "mobile"].includes(profile)) {
  throw new Error("Profile must be either 'perfect' or 'mobile'.");
}
if (!files.length) throw new Error("At least one Lighthouse JSON report is required.");

const limits = profile === "perfect"
  ? {
      performance: 0.995,
      accessibility: 0.95,
      "best-practices": 0.9,
      seo: 0.9,
      "first-contentful-paint": 1000,
      "largest-contentful-paint": 1200,
      "cumulative-layout-shift": 0.01,
      "total-blocking-time": 50,
      "speed-index": 1000,
    }
  : {
      performance: 0.95,
      accessibility: 0.95,
      "best-practices": 0.9,
      seo: 0.9,
      "first-contentful-paint": 2000,
      "largest-contentful-paint": 2500,
      "cumulative-layout-shift": 0.1,
      "total-blocking-time": 200,
      "speed-index": 3000,
    };

const auditChecks = [
  "first-contentful-paint",
  "largest-contentful-paint",
  "cumulative-layout-shift",
  "total-blocking-time",
  "speed-index",
];
const categoryChecks = ["performance", "accessibility", "best-practices", "seo"];

let failed = false;
const summaryRows = [];

for (const file of files) {
  const report = JSON.parse(await readFile(file, "utf8"));
  const url = report.finalDisplayedUrl ?? report.finalUrl ?? file;
  let reportFailed = false;

  const performanceScore = report.categories?.performance?.score ?? 0;
  const displayedPerformance = Math.round(performanceScore * 100);
  if (profile === "perfect" && displayedPerformance !== 100) {
    failed = true;
    reportFailed = true;
    console.error(`Lighthouse FAIL ${url}: displayed performance ${displayedPerformance} != 100`);
  }

  for (const key of categoryChecks) {
    const observed = report.categories?.[key]?.score ?? 0;
    const minimum = limits[key];
    if (observed < minimum) {
      failed = true;
      reportFailed = true;
      console.error(`Lighthouse FAIL ${url}: ${key} ${(observed * 100).toFixed(0)} < ${minimum * 100}`);
    }
  }

  const metrics = {};
  for (const key of auditChecks) {
    const observed = report.audits?.[key]?.numericValue;
    metrics[key] = observed;
    const maximum = limits[key];
    if (typeof observed !== "number" || observed > maximum) {
      failed = true;
      reportFailed = true;
      console.error(`Lighthouse FAIL ${url}: ${key} ${observed ?? "missing"} > ${maximum}`);
    }
  }

  summaryRows.push({
    url,
    performance: displayedPerformance,
    accessibility: Math.round((report.categories?.accessibility?.score ?? 0) * 100),
    bestPractices: Math.round((report.categories?.["best-practices"]?.score ?? 0) * 100),
    seo: Math.round((report.categories?.seo?.score ?? 0) * 100),
    fcp: Math.round(metrics["first-contentful-paint"] ?? 0),
    lcp: Math.round(metrics["largest-contentful-paint"] ?? 0),
    tbt: Math.round(metrics["total-blocking-time"] ?? 0),
    cls: Number(metrics["cumulative-layout-shift"] ?? 0).toFixed(3),
    speedIndex: Math.round(metrics["speed-index"] ?? 0),
    result: reportFailed ? "FAIL" : "PASS",
  });

  if (!reportFailed) {
    console.log(`Lighthouse PASS ${url}: Performance ${displayedPerformance}/100`);
  }
}

const outputDir = path.join(".lighthouseci", profile);
await mkdir(outputDir, { recursive: true });
const lines = [
  `# Lighthouse ${profile === "perfect" ? "100% Performance" : "Mobile"} Report`,
  "",
  "| URL | Performance | Accessibility | Best Practices | SEO | FCP ms | LCP ms | TBT ms | CLS | Speed Index ms | Result |",
  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
  ...summaryRows.map((row) =>
    `| ${row.url} | **${row.performance}%** | ${row.accessibility}% | ${row.bestPractices}% | ${row.seo}% | ${row.fcp} | ${row.lcp} | ${row.tbt} | ${row.cls} | ${row.speedIndex} | **${row.result}** |`,
  ),
  "",
];
await writeFile(path.join(outputDir, "score-summary.md"), lines.join("\n"), "utf8");

if (failed) process.exit(1);
