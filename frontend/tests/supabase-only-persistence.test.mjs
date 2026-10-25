import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const repo = fileURLToPath(new URL("../../", import.meta.url));
const readFront = (path) => readFileSync(new URL(path, `file://${frontend}/`), "utf8");
const readRepo = (path) => readFileSync(new URL(path, `file://${repo}/`), "utf8");

test("student registration writes profiles only through Supabase Auth", () => {
  const actions = readFront("app/auth/actions.ts");
  assert.match(actions, /supabase\.auth\.signUp/);
  assert.doesNotMatch(actions, /\bgetDb\s*\(|\bgetD1\s*\(|\.insert\(studentProfiles\)/);
});

test("contact enquiries use Django only, with no D1 fallback", () => {
  const actions = readFront("app/contact/actions.ts");
  assert.match(actions, /CMS_API_URL/);
  assert.match(actions, /\/enquiries\//);
  assert.doesNotMatch(actions, /getD1|D1Database|contact_enquiries\s*\(/);
  assert.match(actions, /status:\s*"error"/);
});

test("production deployment never binds application services to Render Postgres", () => {
  const render = readRepo("render.yaml");
  assert.doesNotMatch(render, /fromDatabase:/);
  assert.equal((render.match(/key: SUPABASE_ONLY_DATABASE/g) || []).length, 4);
  assert.match(render, /envVarKey: DATABASE_URL/);
});

test("frontend hosting does not request Cloudflare D1", () => {
  const hosting = JSON.parse(readFront(".openai/hosting.json"));
  assert.equal(Object.hasOwn(hosting, "d1"), false);
});
