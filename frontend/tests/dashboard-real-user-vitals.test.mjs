import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("dashboard Core Web Vitals reports no session identifiers and no private URLs", async () => {
  const client = await read("../components/site/dashboard-real-user-vitals.tsx");
  assert.match(client, /useReportWebVitals\(reportDashboardVital\)/);
  assert.match(client, /\["LCP", "INP", "CLS"\]/);
  assert.match(client, /"student_overview"/);
  assert.match(client, /"tutor_dashboard"/);
  assert.match(client, /SAMPLE_RATE = 0\.25/);
  assert.match(client, /credentials: "omit"/);
  assert.match(client, /referrerPolicy: "no-referrer"/);
  assert.match(client, /keepalive: true/);
  assert.doesNotMatch(client, /metric\.id|metric\.entries|access_token|email|localStorage|sessionStorage|location\.href/);
  const layout = await read("../app/layout.tsx");
  assert.match(layout, /<DashboardRealUserVitals \/>/);
});

test("telemetry ingestion allowlists only metric, coarse page and device", async () => {
  const endpoint = await read("../app/api/monitoring/web-vitals/route.ts");
  assert.match(endpoint, /ROUTES = new Set\(/);
  assert.match(endpoint, /METRICS = new Set\(\["LCP", "INP", "CLS"\]\)/);
  assert.match(endpoint, /Object\.keys\(input\)\.sort\(\)\.join\(","\) !== "device,metric,page,value"/);
  assert.match(endpoint, /origin !== new URL\(request\.url\)\.origin/);
  assert.match(endpoint, /acceptedInMinute > 300/);
  assert.match(endpoint, /JSON\.stringify\(\{ page, device, metric, value \}\)/);
  assert.doesNotMatch(endpoint, /request\.headers\.get\("cookie"\)|request\.headers\.get\("authorization"\)|user\.id|session\.user/);
});

test("production tutor acceptance is protected, actually logs in, and does not modify bookings", async () => {
  const workflow = await read("../../.github/workflows/live-tutor-dashboard-acceptance.yml");
  const script = await read("../e2e/live_tutor_dashboard_acceptance.py");
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /environment: tutor-production-verification/);
  assert.match(workflow, /secrets\.AMARIS_LIVE_TEST_TUTOR_EMAIL/);
  assert.match(workflow, /secrets\.AMARIS_LIVE_TEST_TUTOR_PASSWORD/);
  assert.match(script, /page\.wait_for_url\("\*\*\/tutor\/dashboard"/);
  assert.match(script, /Your teaching slots/);
  assert.match(script, /Offer a new live Zoom class/);
  assert.match(script, /page\.reload\(/);
  assert.doesNotMatch(script, /\.screenshot\(|page\.content\(|\.click\(\).*Publish tutor availability/);
});
