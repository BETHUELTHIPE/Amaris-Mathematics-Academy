import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
const src = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("Google login and registration use server-side PKCE with verified callback", () => {
  const login = src("../app/login/page.tsx");
  const register = src("../app/register/page.tsx");
  const actions = src("../app/auth/actions.ts");
  const callback = src("../app/auth/callback/route.ts");
  assert.match(login, /GoogleAuthButton label="Sign in with Google"/);
  assert.match(register, /GoogleAuthButton label="Register with Google"/);
  assert.match(actions, /provider: "google"/);
  assert.match(callback, /exchangeCodeForSession\(code\)/);
  assert.match(callback, /supabase.auth.getUser\(\)/);
  assert.match(callback, /safeRelativePath/);
  assert.match(login, /<form action=\{loginAction\}/);
  assert.match(register, /<form action=\{registerAction\}/);
});

test("paid invoice always uses authenticated student token and private backend", () => {
  const api = src("../lib/student-api.ts");
  const course = src("../app/dashboard/orders/invoice/route.ts");
  const liveClass = src("../app/book-online-live-class/invoice/route.ts");
  const orders = src("../app/dashboard/orders/page.tsx");
  assert.match(api, /getStudentOrders/);
  assert.match(api, /downloadStudentLiveClassInvoice/);
  assert.match(api, /Authorization: `Bearer \$\{token\}`/);
  assert.match(api, /cache: "no-store"/);
  assert.match(course, /requireVerifiedStudent| getStudentIdentity/);
  assert.match(course, /Cache-Control": "private, no-store"/);
  assert.match(liveClass, /requireVerifiedStudent/);
  assert.match(liveClass, /Content-Type": "application\/pdf"/);
  assert.match(orders, /invoice_ready/);
});
