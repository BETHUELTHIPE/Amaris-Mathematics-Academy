import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("October 20 Web Vitals reporting keeps previous dashboard collector", async () => {
  const source = await read("../components/site/dashboard-real-user-vitals.tsx");
  assert.match(source, /useReportWebVitals\(reportDashboardVital\)/);
  assert.match(source, /\/api\/monitoring\/web-vitals/);
  assert.match(source, /NEXT_PUBLIC_ENABLE_WEB_VITALS/);
  assert.match(source, /PUBLIC_RATE = 0\.20/);
  assert.match(source, /pagehide/);
  assert.match(source, /visibilitychange/);
  for (const route of ["home", "courses", "contact", "announcements", "matric", "booking"]) {
    assert.match(source, new RegExp('"' + route + '"'));
  }
  assert.match(source, /credentials: "omit"/);
  assert.match(source, /referrerPolicy: "no-referrer"/);
  assert.match(source, /keepalive: true/);
  assert.match(source, /globalPrivacyControl/);
  assert.match(source, /doNotTrack/);
  assert.doesNotMatch(source, /location\.href|sessionStorage|localStorage|metric\.id|metric\.entries|user\.id/);
});

test("rum beacon rejects cross-origin, unexpected fields and unconfigured backend", async () => {
  const endpoint = await read("../app/api/field-vitals/route.ts");
  assert.match(endpoint, /origin !== new URL\(request\.url\)\.origin/);
  assert.match(endpoint, /site !== "same-origin"/);
  assert.match(endpoint, /Object\.keys\(v\)\.some\(\(field\) => !APPROVED\.has\(field\)\)/);
  assert.match(endpoint, /X-Amaris-Rum-Token/);
  assert.match(endpoint, /process\.env\.RUM_INGEST_TOKEN/);
  assert.match(endpoint, /response\.status === 204 \? 204 : 503/);
  assert.match(endpoint, /AbortSignal\.timeout\(3000\)/);
  assert.doesNotMatch(endpoint, /console\.(log|info)\(|authorization|request\.headers\.get\("cookie"\)/);
});

test("performance privacy disclosure explains sampling and user choices", async () => {
  const privacy = await read("../app/privacy/page.tsx");
  assert.match(privacy, /Anonymous browser performance/);
  assert.match(privacy, /20%/);
  assert.match(privacy, /Do Not Track/);
  assert.match(privacy, /Global Privacy Control/);
});
