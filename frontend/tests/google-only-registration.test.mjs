import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const registration = source("../app/register/page.tsx");
const login = source("../app/login/page.tsx");
const actions = source("../app/auth/actions.ts");
const callback = source("../app/auth/callback/route.ts");
const button = source("../components/site/google-auth-button.tsx");
const identity = source("../lib/auth.ts");

test("registration shows Google as the only social provider", () => {
  assert.match(registration, /GoogleAuthButton label="Register with Google"/);
  assert.doesNotMatch(registration, /LinkedInAuthButton|FacebookAuthButton|GitHubAuthButton|Register with (LinkedIn|Facebook|GitHub)/);
  assert.match(registration, /<form action=\{registerAction\}/);
  assert.match(registration, /name="terms"/);
});

test("returning Google students can sign in and email/password remains available", () => {
  assert.match(login, /GoogleAuthButton label="Continue with Google"/);
  assert.match(login, /<form action=\{loginAction\}/);
  assert.doesNotMatch(login, /LinkedInAuthButton|FacebookAuthButton|GitHubAuthButton/);
});

test("Google OAuth is the only social sign-in action and redirects through a local callback", () => {
  assert.match(button, /action=\{googleAuthAction\}/);
  assert.match(actions, /provider: "google"/);
  assert.match(actions, /safeRelativePath\(String\(formData.get\("next"\)/);
  assert.match(actions, /getSiteUrl\(\)\}\/auth\/callback/);
  assert.doesNotMatch(actions, /provider: "(facebook|github|linkedin_oidc|twitter|apple)"/);
});

test("callback verifies the session and confines redirects to safe relative paths", () => {
  assert.match(callback, /exchangeCodeForSession\(code\)/);
  assert.match(callback, /supabase.auth.getUser\(\)/);
  assert.match(callback, /safeRelativePath\(/);
  assert.match(callback, /email_confirmed_at/);
});


test("verified student identity uses the authoritative Supabase user record", () => {
  assert.match(identity, /supabase\.auth\.getClaims\(\)/);
  assert.match(identity, /supabase\.auth\.getUser\(\)/);
  assert.match(identity, /userData\.user\.id !== data\.claims\.sub/);
  assert.match(identity, /Boolean\(userData\.user\.email_confirmed_at\)/);
  assert.doesNotMatch(identity, /claims\.email_verified/);
});
