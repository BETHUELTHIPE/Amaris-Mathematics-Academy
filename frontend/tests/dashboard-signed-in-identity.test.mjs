import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const read = relative => readFileSync(new URL(relative, import.meta.url), "utf8");
const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  configFile: false,
  appType: "custom",
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { DashboardAccountIdentity } = await vite.ssrLoadModule("/components/site/dashboard-account-identity.tsx");
after(() => vite.close());

test("student and tutor dashboard headers show full name and signed-in email together", () => {
  const identity = { displayName: "Nandi van der Merwe", email: "nandi@example.test" };
  for (const role of ["Student", "Tutor"]) {
    const html = renderToStaticMarkup(React.createElement(DashboardAccountIdentity, { identity, role }));
    assert.match(html, /Signed-in account/);
    assert.match(html, /Nandi van der Merwe/);
    assert.match(html, /nandi@example\.test/);
    assert.ok(html.includes(role));
  }
});

test("user-provided names are rendered safely and are not embedded in script", () => {
  const html = renderToStaticMarkup(React.createElement(DashboardAccountIdentity, {
    identity: { displayName: "<script>alert(1)</script>", email: "verified@example.test" }, role: "Student",
  }));
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /verified@example\.test/);
});

test("every student dashboard page passes the verified account from its server auth gate", () => {
  const shell = read("../components/site/student-dashboard-shell.tsx");
  assert.match(shell, /<DashboardAccountIdentity identity=\{identity\} role="Student"/);
  assert.match(shell, /headerAside/);
  const pages = [
    ["../app/dashboard/page.tsx", "overview", "/dashboard"],
    ["../app/dashboard/orders/page.tsx", "orders", "/dashboard/orders"],
    ["../app/dashboard/notifications/page.tsx", "notifications", "/dashboard/notifications"],
  ];
  for (const [path, active, route] of pages) {
    const src = read(path);
    assert.ok(src.includes('const user = await requireVerifiedStudent("'+route+'")'), path);
    assert.match(src, /<StudentDashboardShell/);
    assert.match(src, /identity=\{user\}/);
    assert.ok(src.includes('active="'+active+'"'));
    assert.match(src, /force-dynamic/);
  }
});

test("tutor dashboard uses verified logged-in email and role-checked profile name", () => {
  const tutor = read("../app/tutor/dashboard/page.tsx");
  assert.match(tutor, /const identity = await getStudentIdentity\(\)/);
  assert.match(tutor, /if \(!identity\.emailVerified\)/);
  assert.match(tutor, /dashboard = await getTutorDashboard\(\)/);
  assert.match(tutor, /email: identity\.email/);
  assert.match(tutor, /DashboardAccountIdentity identity=\{tutorIdentity\} role="Tutor"/);
  assert.doesNotMatch(tutor, /email: dashboard\.tutor\.email/);
  assert.match(tutor, /force-dynamic/);
});

test("identity comes from authoritative Supabase getUser record, not submitted fields", () => {
  const auth = read("../lib/auth.ts");
  assert.match(auth, /await supabase\.auth\.getUser\(\)/);
  assert.match(auth, /mapClaims\(data\.claims, userData\.user\)/);
  assert.match(auth, /verifiedUser\.user_metadata/);
  assert.match(auth, /verifiedUser\.email/);
  assert.match(auth, /emailVerified: Boolean\(verifiedUser\.email_confirmed_at\)/);
  assert.match(auth, /Name not provided/);
});
