import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const actionsPath = fileURLToPath(new URL("../app/auth/actions.ts", import.meta.url));
const loginPath = fileURLToPath(new URL("../app/login/page.tsx", import.meta.url));
const registerPath = fileURLToPath(new URL("../app/register/page.tsx", import.meta.url));

const [actionsSource, loginSource, registerSource] = await Promise.all([
  readFile(actionsPath, "utf8"),
  readFile(loginPath, "utf8"),
  readFile(registerPath, "utf8"),
]);

test("all configured student social providers use Supabase OAuth", () => {
  assert.match(actionsSource, /provider:\s*"google"/);
  assert.match(actionsSource, /provider:\s*"linkedin_oidc"/);
  assert.match(actionsSource, /provider:\s*"facebook"/);
  assert.match(actionsSource, /provider:\s*"github"/);
  const callbackMatches = actionsSource.match(/\/auth\/callback\?next=/g) ?? [];
  assert.ok(callbackMatches.length >= 4);
});

test("student login exposes Google LinkedIn Facebook and GitHub", () => {
  assert.match(loginSource, /Continue with Google/);
  assert.match(loginSource, /Continue with LinkedIn/);
  assert.match(loginSource, /Continue with Facebook/);
  assert.match(loginSource, /Continue with GitHub/);
});

test("student registration exposes Google LinkedIn Facebook and GitHub", () => {
  assert.match(registerSource, /Register with Google/);
  assert.match(registerSource, /Register with LinkedIn/);
  assert.match(registerSource, /Register with Facebook/);
  assert.match(registerSource, /Register with GitHub/);
});
