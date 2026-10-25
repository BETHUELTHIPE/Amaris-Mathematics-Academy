import assert from "node:assert/strict";
import test, { after } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  appType: "custom",
  configFile: false,
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { hasVerifiedAccountEmail } = await vite.ssrLoadModule("/lib/verified-account-email.ts");
after(() => vite.close());

function auth(confirmation) {
  const events = [];
  const service = {
    getUser: async () => {
      events.push("getUser");
      if (confirmation === "throws") throw new Error("auth network unavailable");
      return {
        data: { user: confirmation === "missing" ? null : { email_confirmed_at: confirmation === "verified" ? "2026-10-25T19:27:48Z" : null } },
        error: confirmation === "errors" ? { message: "Auth failed" } : null,
      };
    },
    signOut: async value => { events.push({ signOut: value }); return { error: null }; },
  };
  return { service, events };
}

test("verified student, tutor, sponsor or any other existing role remains signed in", async () => {
  for (const role of ["student", "tutor", "sponsor", "staff", "other"]) {
    const { service, events } = auth("verified");
    assert.equal(await hasVerifiedAccountEmail(service), true, role);
    assert.deepEqual(events, ["getUser"], role);
  }
});

test("unverified account is signed out locally before protected access", async () => {
  const { service, events } = auth("unverified");
  assert.equal(await hasVerifiedAccountEmail(service), false);
  assert.deepEqual(events, ["getUser", { signOut: { scope: "local" } }]);
});

test("missing user, Auth error or Auth outage fail closed", async () => {
  for (const condition of ["missing", "errors", "throws"]) {
    const { service, events } = auth(condition);
    assert.equal(await hasVerifiedAccountEmail(service), false, condition);
    assert.deepEqual(events.at(-1), { signOut: { scope: "local" } });
  }
});

test("even failed session cleanup does not grant access", async () => {
  const client = {
    getUser: async () => ({ data: { user: { email_confirmed_at: null } }, error: null }),
    signOut: async () => { throw new Error("Session cleanup failed"); },
  };
  assert.equal(await hasVerifiedAccountEmail(client), false);
});

test("all current website entry points require authoritative confirmed email", () => {
  const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
  const student = read("../app/auth/actions.ts");
  const tutor = read("../app/tutor/actions.ts");
  const applicant = read("../app/tutor/register/actions.ts");
  const google = read("../app/auth/callback/route.ts");
  const link = read("../app/auth/confirm/route.ts");
  const backend = read("../../backend/content/authentication.py");
  const tutorApi = read("../lib/tutor-api.ts");
  const applicantApi = read("../lib/tutor-applications.ts");
  const authState = read("../app/api/auth-state/route.ts");
  assert.match(student, /hasVerifiedAccountEmail\(supabase\.auth\)/);
  assert.match(tutor, /hasVerifiedAccountEmail\(supabase\.auth\)/);
  assert.equal((applicant.match(/hasVerifiedAccountEmail\(supabase\.auth\)/g) || []).length, 2);
  assert.match(google, /user\?\.email_confirmed_at/);
  assert.match(google, /signOut\(\{ scope: "local" \}\)/);
  assert.match(link, /hasVerifiedAccountEmail\(supabase\.auth\)/);
  assert.match(backend, /email_confirmed_at/);
  assert.match(tutorApi, /user\.email_confirmed_at/);
  assert.match(applicantApi, /email_confirmed_at/);
  assert.match(authState, /authenticated: Boolean\(student\?\.emailVerified\)/);
});
