// Reads existing Render log exports from stdin and prints ONLY coarse aggregates.
// No customer records, URLs, event IDs or raw log lines are displayed or persisted.
// Usage: node scripts/performance/summarize-dashboard-vitals.mjs < render-logs.txt
import { createInterface } from "node:readline";

const PREFIX = "amaris_dashboard_vital ";
const METRICS = new Set(["LCP", "INP", "CLS"]);
const DEVICES = new Set(["mobile", "desktop"]);
const PAGES = new Set(["home", "courses", "announcements", "contact", "matric_upgrades", "booking", "student_overview", "student_orders", "student_notifications", "tutor_dashboard"]);

export function p75(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(0.75 * sorted.length) - 1)];
}

export function parseVitalLine(line) {
  const offset = line.indexOf(PREFIX);
  if (offset === -1) return null;
  try {
    const { page, metric, device, value, release } = JSON.parse(line.slice(offset + PREFIX.length));
    if (!PAGES.has(page) || !METRICS.has(metric) || !DEVICES.has(device) ||
        typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
    // Older events lack a release marker; keep them separate from verified SHAs.
    const safeRelease = typeof release === "string" && /^[a-f0-9]{7,40}$/i.test(release)
      ? release.toLowerCase().slice(0, 12) : "unknown";
    return { page, metric, device, value, release: safeRelease };
  } catch {
    return null;
  }
}

export function summarize(records) {
  const buckets = new Map();
  for (const record of records) {
    const key = [record.release || "unknown", record.page, record.device, record.metric].join(" / ");
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(record.value);
  }
  return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, values]) => {
    const metric = key.split(" / ")[3];
    const threshold = metric === "CLS" ? 0.1 : metric === "LCP" ? 2500 : 200;
    const value = p75(values);
    return { key, count: values.length, p75: value, threshold,
      acceptance: values.length < 100 ? "INSUFFICIENT SAMPLE" : value <= threshold ? "TARGET MET" : "NEEDS IMPROVEMENT" };
  });
}

if (process.argv[1]?.endsWith("summarize-dashboard-vitals.mjs")) {
  const collected = [];
  for await (const line of createInterface({ input: process.stdin })) {
    const record = parseVitalLine(line);
    if (record) collected.push(record);
  }
  console.log("release / page / device / metric | samples | p75 | target | status");
  for (const r of summarize(collected)) {
    console.log(`${r.key} | ${r.count} | ${r.p75} | ${r.threshold} | ${r.acceptance}`);
  }
  if (!collected.length) console.log("NO VERIFIED FIELD DATA: do not claim real-user p75 or improvement");
}
