// Diagnostic companion to the *unchanged* Lighthouse 100/100 acceptance gate.
// This script only reads reports and prints their bottlenecks; it never
// mutates scores or affects acceptance thresholds.
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const reportDir = process.argv[2] ?? ".lighthouseci/mobile";
const files = (await readdir(reportDir).catch((error) => {
  if (error.code === "ENOENT") return [];
  throw error;
})).filter((file) => /^(home|courses|contact)-[1-3](?:\.report)?\.json$/.test(file)).sort();
if (!files.length) {
  console.log("No retained Lighthouse JSON reports were found for diagnosis.");
  process.exit(0);
}

function ms(value) {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value) + " ms" : "unavailable";
}
function kib(value) {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value / 1024) + " KiB" : "unavailable";
}
function median(values) {
  const nums = values.filter((value) => typeof value === "number" && Number.isFinite(value)).sort((a, b) => a - b);
  if (!nums.length) return null;
  const middle = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[middle] : (nums[middle - 1] + nums[middle]) / 2;
}
function safePublicPath(url) {
  try {
    const parsed = new URL(url);
    // Never write query strings, userinfo, signed URLs, credentials or origin to reports.
    return parsed.pathname || "/";
  } catch {
    return "[unknown]";
  }
}
const groups = new Map();
for (const file of files) {
  const report = JSON.parse(await readFile(path.join(reportDir, file), "utf8"));
  const route = safePublicPath(report.finalDisplayedUrl || report.finalUrl || "/");
  const known = groups.get(route) ?? [];
  known.push({ file, report });
  groups.set(route, known);
}

const lines = [
  "# Lighthouse mobile bottleneck diagnosis",
  "",
  "These are *laboratory estimates* from retained Lighthouse reports, not field Core Web Vitals. The mandatory 100/100 acceptance threshold is unchanged.",
  "",
  "| Route | Median score | Median LCP | Median TBT | Median unused-JS opportunity |",
  "| --- | ---: | ---: | ---: | ---: |",
];

for (const [route, samples] of [...groups].sort(([a], [b]) => a.localeCompare(b))) {
  const audits = samples.map(({ report }) => report.audits ?? {});
  const lcp = median(audits.map((a) => a["largest-contentful-paint"]?.numericValue));
  const tbt = median(audits.map((a) => a["total-blocking-time"]?.numericValue));
  const unused = median(audits.map((a) => {
    const details = a["unused-javascript"]?.details;
    if (Number.isFinite(details?.overallSavingsBytes)) return details.overallSavingsBytes;
    if (Array.isArray(details?.items)) return details.items.reduce(
      (sum, item) => sum + (Number.isFinite(item.wastedBytes) ? item.wastedBytes : 0), 0
    );
    return null;
  }));
  const performance = median(samples.map(({ report }) => report.categories?.performance?.score));
  lines.push(`| ${route} | ${performance === null ? "unavailable" : Math.round(performance * 100) + "/100"} | ${ms(lcp)} | ${ms(tbt)} | ${kib(unused)} |`);
}

for (const [route, samples] of [...groups].sort(([a], [b]) => a.localeCompare(b))) {
  // Use the median-score report rather than cherry-picking a fast outlier.
  const scored = [...samples].sort((a, b) => (a.report.categories?.performance?.score ?? 0) - (b.report.categories?.performance?.score ?? 0));
  const selected = scored[Math.floor(scored.length / 2)];
  const audits = selected.report.audits ?? {};
  lines.push("", `## ${route}`, "", `Representative report: ${selected.file} (median score)`, "");

  const items = (audits["unused-javascript"]?.details?.items ?? [])
    .filter((item) => Number.isFinite(item.wastedBytes) && item.wastedBytes > 0)
    .sort((a, b) => b.wastedBytes - a.wastedBytes)
    .slice(0, 8);
  lines.push("### Potentially unused JavaScript", "", "| Public asset path | Estimated unused | Total transfer |", "| --- | ---: | ---: |");
  if (!items.length) lines.push("| Not reported | — | — |");
  for (const item of items) {
    lines.push(`| ${safePublicPath(item.url || "")} | ${kib(item.wastedBytes)} | ${kib(item.totalBytes)} |`);
  }

  const tasks = (audits["mainthread-work-breakdown"]?.details?.items ?? [])
    .filter((item) => Number.isFinite(item.duration))
    .sort((a, b) => b.duration - a.duration)
    .slice(0, 7);
  lines.push("", "### Main-thread work", "", "| Group | Duration |", "| --- | ---: |");
  if (!tasks.length) lines.push("| Not reported | — |");
  for (const item of tasks) {
    const label = String(item.groupLabel ?? item.group ?? "Other").replaceAll("|", "/").replaceAll("\n", " ").slice(0, 80);
    lines.push(`| ${label} | ${ms(item.duration)} |`);
  }

  const lcpAudit = audits["largest-contentful-paint-element"];
  const candidate = lcpAudit?.details?.items?.[0]?.node?.snippet;
  if (typeof candidate === "string" && candidate.length) {
    // HTML snippet can contain URL parameters; report only the tag name, not raw HTML.
    const tagName = candidate.match(/^\s*<([a-zA-Z][\w-]*)/)?.[1] ?? "unknown";
    lines.push("", `LCP element tag: **${tagName}** (full details retained in the original JSON).`);
  }
}
lines.push("", "Next: profile the highest unused JS sources and long main-thread work before changing shared navigation or protected student/payment flows.", "");
const content = lines.join("\n");
await writeFile(path.join(reportDir, "bottleneck-summary.md"), content, "utf8");
console.log(content);
