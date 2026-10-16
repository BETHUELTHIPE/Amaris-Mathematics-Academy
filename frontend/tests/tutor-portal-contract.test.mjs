import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (file) => fs.readFileSync(new URL(file, import.meta.url), "utf8");
const login = read("../app/tutor/login/page.tsx");
const page = read("../app/tutor/dashboard/page.tsx");
const actions = read("../app/tutor/actions.ts");
const api = read("../lib/tutor-api.ts");
const nav = read("../lib/navigation.ts");

test("tutor access is visible without mixing into student dashboard", () => {
  assert.match(nav, /url: "\/tutor\/login"/);
  assert.match(login, /tutorLoginAction/);
  assert.match(actions, /supabase.auth.signInWithPassword/);
  assert.match(login, /GoogleAuthButton/);
  assert.match(login, /next="\/tutor\/dashboard"/);
});

test("tutor dashboard requires verified Supabase identity and backend role gate", () => {
  assert.match(api, /supabase\.auth\.getUser\(\)/);
  assert.match(api, /user\.email_confirmed_at/);
  assert.match(api, /Authorization: `Bearer \$\{token\}`/);
  assert.match(api, /cache: "no-store"/);
  assert.doesNotMatch(page, /SUPABASE_SERVICE_ROLE_KEY|OPENAI_API_KEY/);
});

test("self-service form supports multi-hour tutor sessions and private Zoom link", () => {
  assert.match(page, /duration_hours/);
  assert.match(page, /max=\{24\}/);
  assert.match(page, /starts_at/);
  assert.match(page, /zoom_join_url/);
  assert.match(page, /createTutorSlotAction/);
  assert.match(page, /updateTutorSlotAction/);
  assert.match(page, /pauseTutorSlotAction/);
  assert.match(page, /booking\.student_email/);
  assert.match(page, /booking\.zoom_join_url/);
  assert.match(page, /Africa\/Johannesburg/);
});

test("all tutor modifications run in server actions, without browser-owned price or owner", () => {
  assert.match(actions, /^"use server"/);
  assert.match(actions, /cleanStart/);
  assert.match(actions, /duration_hours: duration/);
  assert.match(actions, /is_active: form\.get/);
  assert.doesNotMatch(actions, /amount|tutor_id|student_id/);
  assert.match(api, /"POST"/);
  assert.match(api, /"PATCH"/);
});
