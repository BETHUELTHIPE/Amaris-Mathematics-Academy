import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../lib/analytics.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { analyticsDays, analyticsCsv, groupedSeries, validateAnalytics, chartTypes, formatMetric } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);

function fixture() {
  const series = Array.from({ length: 7 }, (_, index) => ({ date: `2026-11-0${index + 1}`, value: index }));
  return { version: 1, role: "student", generated_at: "2026-11-07T12:00:00Z", period: { days: 7, start: "2026-11-01", end: "2026-11-07", timezone: "Africa/Johannesburg" },
    metrics: ["paid_services", "spending", "lesson_hours", "video_requests"].map(key => ({ key, title: key, unit: "count", description: "Synthetic contract fixture", total: 21, series, breakdown: [{ label: "Courses", value: 21 }] })),
    progress: { title: "Saved progress", percent: 50, completed: 1, total: 2, description: "Current enrolments" } };
}

test("all four requested chart types are available; range filters are bounded", () => {
  assert.deepEqual(chartTypes.map(type => type.key), ["line", "bar", "pie", "gauge"]);
  assert.equal(analyticsDays("7"), 7); assert.equal(analyticsDays("90"), 90); assert.equal(analyticsDays("50000"), 30);
});
test("weekly grouping conserves totals and partial weeks", () => {
  const series = Array.from({ length: 30 }, (_, i) => ({ date: new Date(Date.UTC(2026, 9, i + 1)).toISOString().slice(0, 10), value: i }));
  const result = groupedSeries(series);
  assert.equal(result.length, 5);
  assert.equal(result.reduce((sum, row) => sum + row.value, 0), series.reduce((sum, row) => sum + row.value, 0));
  assert.equal(groupedSeries(series.slice(0, 7)).length, 7);
});
test("payload validation binds role, rejects inconsistent data and strips unexpected private fields", () => {
  const data = fixture();
  const result = validateAnalytics({ ...data, bank_account_number: "never-client-visible" }, "student");
  assert.equal(result.metrics[0].total, 21);
  assert.equal("bank_account_number" in result, false);
  assert.throws(() => validateAnalytics(data, "tutor"));
  for (const patch of [{ version: 2 }, { progress: { ...data.progress, percent: 101 } }, { period: { ...data.period, days: 1 } }, { metrics: [{ ...data.metrics[0], total: 999 }, ...data.metrics.slice(1)] }]) {
    assert.throws(() => validateAnalytics({ ...data, ...patch }, "student"));
  }
});
test("CSV exports actual daily values in rands and neutralizes spreadsheet formulas", () => {
  const data = fixture(); data.metrics[0].title = '=HYPERLINK("invalid")'; data.metrics[0].unit = "cents";
  const csv = analyticsCsv(data);
  assert.ok(csv.startsWith("\uFEFF")); assert.ok(csv.includes("'=")); assert.ok(csv.includes('"0.06","ZAR"'));
  assert.equal(/student_email|student_id|bank_account|access_token/.test(csv), false);
  assert.match(formatMetric(12345, "cents"), /123[.,]45/);
});
test("no fabricated live data or client-side backend credentials; private role routes exist", () => {
  const component = readFileSync(new URL("../components/site/analytics-dashboard.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(component, /Math\.random|SUPABASE_SERVICE|AIRFLOW_API_TOKEN|process\.env|fetch\(/);
  assert.match(component, /ResizeObserver/); assert.match(component, /View the exact daily data/);
  const student = readFileSync(new URL("../app/dashboard/analytics/page.tsx", import.meta.url), "utf8");
  const tutor = readFileSync(new URL("../app/tutor/analytics/page.tsx", import.meta.url), "utf8");
  assert.match(student, /requireVerifiedStudent/); assert.match(tutor, /getTutorAnalytics/); assert.match(tutor, /emailVerified/);
  assert.match(student, /AnalyticsUnavailable/); assert.match(tutor, /AnalyticsUnavailable/);
});
