import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const [profile, ...files] = process.argv.slice(2);
if (!profile || !["perfect", "mobile"].includes(profile)) {
  throw new Error("Profile must be either 'perfect' or 'mobile'.");
}
if (!files.length) throw new Error("At least one Lighthouse JSON report is required.");

const limits = profile === "perfect"
  ? {
      performance: 1,
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
      performance: 1,
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

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
};

const reports = [];
for (const file of files) {
  const report = JSON.parse(await readFile(file, "utf8"));
  const url = report.finalDisplayedUrl ?? report.finalUrl ?? file;
  const metrics = Object.fromEntries(
    auditChecks.map((key) => [key, report.audits?.[key]?.numericValue]),
  );
  reports.push({
    file,
    url,
    categories: Object.fromEntries(
      categoryChecks.map((key) => [key, report.categories?.[key]?.score ?? 0]),
    ),
    metrics,
  });
}

const groups = new Map();
for (const report of reports) {
  const existing = groups.get(report.url) ?? [];
  existing.push(report);
  groups.set(report.url, existing);
}

let failed = false;
const aggregateRows = [];
const sampleRows = [];

for (const [url, samples] of groups) {
  if (samples.length !== 3) {
    failed = true;
    console.error(`Lighthouse FAIL ${url}: expected exactly 3 retained runs, found ${samples.length}`);
  }

  for (const sample of samples) {
    const performanceScore = sample.categories.performance;
    const displayedPerformance = Math.round(performanceScore * 100);
    const sampleWithinLimits =
      displayedPerformance === 100 &&
      performanceScore >= 1 &&
      categoryChecks.every((key) => sample.categories[key] >= limits[key]) &&
      auditChecks.every((key) => {
        const value = sample.metrics[key];
        return typeof value === "number" && value <= limits[key];
      });

    sampleRows.push({
      url,
      file: path.basename(sample.file),
      performance: displayedPerformance,
      accessibility: Math.round(sample.categories.accessibility * 100),
      bestPractices: Math.round(sample.categories["best-practices"] * 100),
      seo: Math.round(sample.categories.seo * 100),
      fcp: Math.round(sample.metrics["first-contentful-paint"] ?? 0),
      lcp: Math.round(sample.metrics["largest-contentful-paint"] ?? 0),
      tbt: Math.round(sample.metrics["total-blocking-time"] ?? 0),
      cls: Number(sample.metrics["cumulative-layout-shift"] ?? 0).toFixed(3),
      speedIndex: Math.round(sample.metrics["speed-index"] ?? 0),
      result: sampleWithinLimits ? "100 SAMPLE" : "RAW OUTLIER",
    });
  }

  const medianCategories = Object.fromEntries(
    categoryChecks.map((key) => [key, median(samples.map((sample) => sample.categories[key]))]),
  );
  const medianMetrics = Object.fromEntries(
    auditChecks.map((key) => {
      const values = samples.map((sample) => sample.metrics[key]);
      return [
        key,
        values.every((value) => typeof value === "number") ? median(values) : Number.NaN,
      ];
    }),
  );

  let groupFailed = false;
  const displayedPerformance = Math.round(medianCategories.performance * 100);
  if (displayedPerformance !== 100 || medianCategories.performance < 1) {
    groupFailed = true;
    console.error(
      `Lighthouse FAIL ${url}: median performance ${(medianCategories.performance * 100).toFixed(1)}%, displayed ${displayedPerformance}% — median 100% is required`,
    );
  }

  for (const key of categoryChecks) {
    const observed = medianCategories[key];
    const minimum = limits[key];
    if (observed < minimum) {
      groupFailed = true;
      console.error(`Lighthouse FAIL ${url}: median ${key} ${(observed * 100).toFixed(0)} < ${minimum * 100}`);
    }
  }

  for (const key of auditChecks) {
    const observed = medianMetrics[key];
    const maximum = limits[key];
    if (!Number.isFinite(observed) || observed > maximum) {
      groupFailed = true;
      console.error(`Lighthouse FAIL ${url}: median ${key} ${Number.isFinite(observed) ? observed : "missing"} > ${maximum}`);
    }
  }

  if (groupFailed) failed = true;
  else console.log(`Lighthouse PASS ${url}: median Performance 100/100 across 3 retained runs`);

  aggregateRows.push({
    url,
    performance: displayedPerformance,
    accessibility: Math.round(medianCategories.accessibility * 100),
    bestPractices: Math.round(medianCategories["best-practices"] * 100),
    seo: Math.round(medianCategories.seo * 100),
    fcp: Math.round(medianMetrics["first-contentful-paint"] ?? 0),
    lcp: Math.round(medianMetrics["largest-contentful-paint"] ?? 0),
    tbt: Math.round(medianMetrics["total-blocking-time"] ?? 0),
    cls: Number(medianMetrics["cumulative-layout-shift"] ?? 0).toFixed(3),
    speedIndex: Math.round(medianMetrics["speed-index"] ?? 0),
    result: groupFailed ? "FAIL" : "PASS",
  });
}

const outputDir = path.join(".lighthouseci", profile);
await mkdir(outputDir, { recursive: true });
const lines = [
  `# Lighthouse ${profile === "perfect" ? "Desktop" : "Mobile"} 100% Performance Report`,
  "",
  "Performance is PASS only when the median of 3 retained Lighthouse runs for every tested URL is exactly 1.00 (100/100), with the same metric/category limits applied to the median. All raw runs are retained below so noisy outliers remain visible.",
  "",
  "## Acceptance result (median of 3)",
  "",
  "| URL | Performance | Accessibility | Best Practices | SEO | FCP ms | LCP ms | TBT ms | CLS | Speed Index ms | Result |",
  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
  ...aggregateRows.map((row) =>
    `| ${row.url} | **${row.performance}%** | ${row.accessibility}% | ${row.bestPractices}% | ${row.seo}% | ${row.fcp} | ${row.lcp} | ${row.tbt} | ${row.cls} | ${row.speedIndex} | **${row.result}** |`,
  ),
  "",
  "## Raw retained samples",
  "",
  "| URL | Report | Performance | Accessibility | Best Practices | SEO | FCP ms | LCP ms | TBT ms | CLS | Speed Index ms | Sample |",
  "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
  ...sampleRows.map((row) =>
    `| ${row.url} | ${row.file} | **${row.performance}%** | ${row.accessibility}% | ${row.bestPractices}% | ${row.seo}% | ${row.fcp} | ${row.lcp} | ${row.tbt} | ${row.cls} | ${row.speedIndex} | ${row.result} |`,
  ),
  "",
];
await writeFile(path.join(outputDir, "score-summary.md"), lines.join("\n"), "utf8");

if (failed) process.exit(1);
