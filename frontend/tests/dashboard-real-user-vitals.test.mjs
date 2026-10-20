import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { p75, parseVitalLine, summarize } from "../scripts/performance/summarize-dashboard-vitals.mjs";

const read = (name) => readFile(new URL(name, import.meta.url), "utf8");

test("public and dashboard Web Vitals use coarse allowlisted routes without identifying visitors", async () => {
  const client = await read("../components/site/dashboard-real-user-vitals.tsx");
  assert.match(client, /useReportWebVitals\(reportDashboardVital\)/);
  assert.match(client, /\["LCP", "INP", "CLS"\]/);
  for (const route of ["home", "courses", "announcements", "contact", "matric_upgrades", "booking"]) {
    assert.ok(client.includes(`"${route}"`), `missing public route ${route}`);
  }
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
  assert.match(endpoint, /JSON\\.stringify\\(\\{ page, device, metric, value, release \\}\\)/);
  assert.match(endpoint, /process\\.env\\.RENDER_GIT_COMMIT/);
  assert.match(endpoint, /"home", "courses", "announcements"/);
  assert.doesNotMatch(endpoint, /request\.headers\.get\("cookie"\)|request\.headers\.get\("authorization"\)|user\.id|session\.user/);
});

test("production tutor acceptance is protected, actually logs in, and does not modify bookings", async () => {
  const workflow = await read("../../.github/workflows/verified-production-tutor-session.yml");
  const script = await read("../e2e/live_tutor_dashboard_acceptance.py");
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /github.ref_name == 'main'/);
  assert.match(workflow, /environment: tutor-production-verification/);
  assert.match(workflow, /secrets\.AMARIS_LIVE_TEST_TUTOR_EMAIL/);
  assert.match(workflow, /secrets\.AMARIS_LIVE_TEST_TUTOR_PASSWORD/);
  assert.match(script, /page\.wait_for_url\("\*\*\/tutor\/dashboard"/);
  assert.match(script, /Your teaching slots/);
  assert.match(script, /Offer a new live Zoom class/);
  assert.match(script, /page\.reload\(/);
  assert.doesNotMatch(script, /\.screenshot\(|page\.content\(|\.click\(\).*Publish tutor availability/);
});

test("field aggregator computes per-route p75 without exposing raw users", () => {
  assert.equal(p75([25, 7, 19, 3]), 19);
  const release = "e2025cb3b807";
  const parse = parseVitalLine(`amaris_dashboard_vital {"page":"home","device":"mobile","metric":"LCP","value":1890,"release":"${release}"}`);
  assert.deepEqual(parse, {page:"home",device:"mobile",metric:"LCP",value:1890,release});
  assert.equal(parseVitalLine('amaris_dashboard_vital {"page":"/orders/123","device":"mobile","metric":"INP","value":30}'), null);
  assert.equal(p75([]), null);
  assert.equal(parseVitalLine('ignored log line containing account info'), null);
  assert.equal(parseVitalLine('amaris_dashboard_vital {"page":"tutor_dashboard","device":"desktop","metric":"INP","value":145}').value, 145);
  assert.equal(parseVitalLine('amaris_dashboard_vital {"page":"/dashboard?user=email","device":"desktop","metric":"INP","value":145}'), null);
  const measurements = Array.from({length:100}, () => ({page:"tutor_dashboard",device:"mobile",metric:"CLS",value:0.04}));
  const result = summarize(measurements);
  assert.equal(result.length, 1);
  assert.equal(result[0].count, 100);
  assert.equal(result[0].key, "unknown / tutor_dashboard / mobile / CLS");
  assert.equal(result[0].p75, 0.04);
  assert.equal(result[0].acceptance, "TARGET MET");
  assert.equal(summarize(measurements.slice(0, 20))[0].acceptance, "INSUFFICIENT SAMPLE");
});
