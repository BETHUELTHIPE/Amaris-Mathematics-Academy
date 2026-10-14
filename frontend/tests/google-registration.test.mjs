import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { getSiteUrl } from "../lib/supabase/config.ts";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const registration = source("../app/register/page.tsx");
const login = source("../app/login/page.tsx");
const actions = source("../app/auth/actions.ts");
const callback = source("../app/auth/callback/route.ts");
const button = source("../components/site/google-auth-button.tsx");
const completeProfile = source("../app/complete-profile/page.tsx");
const identity = source("../lib/auth.ts");

test("students can choose Google registration while email registration remains available", () => {
  assert.match(registration, /GoogleAuthButton label="Register with Google"/);
  assert.match(registration, /<form action=\{registerAction\}/);
  assert.match(registration, /name="terms"/);
  assert.match(button, /By continuing with Google, you agree/);
});

test("returning Google students can sign in and email login remains available", () => {
  assert.match(login, /GoogleAuthButton label="Continue with Google"/);
  assert.match(login, /<form action=\{loginAction\}/);
});

test("Google OAuth redirects through the local PKCE callback", () => {
  assert.match(button, /action=\{googleAuthAction\}/);
  assert.match(actions, /provider: "google"/);
  assert.match(actions, /safeRelativePath\(String\(formData.get\("next"\)/);
  assert.match(actions, /getSiteUrl\(\)\}\/auth\/callback/);
});

test("callback verifies the session and confines redirects to safe relative paths", () => {
  assert.match(callback, /exchangeCodeForSession\(code\)/);
  assert.match(callback, /supabase.auth.getUser\(\)/);
  assert.match(callback, /safeRelativePath\(/);
  assert.match(callback, /email_confirmed_at/);
});

test("verified student identity uses the authoritative Supabase user record and Google names", () => {
  assert.match(identity, /supabase\.auth\.getClaims\(\)/);
  assert.match(identity, /supabase\.auth\.getUser\(\)/);
  assert.match(identity, /userData\.user\.id !== data\.claims\.sub/);
  assert.match(identity, /Boolean\(userData\.user\.email_confirmed_at\)/);
  assert.match(identity, /metadata\.given_name/);
  assert.match(identity, /metadata\.family_name/);
  assert.doesNotMatch(identity, /claims\.email_verified/);
});

test("Google callback uses the current Render service origin unless SITE_URL overrides it", () => {
  const originalSite = process.env.SITE_URL;
  const originalRender = process.env.RENDER_EXTERNAL_URL;
  try {
    delete process.env.SITE_URL;
    process.env.RENDER_EXTERNAL_URL = "https://staging-students.onrender.com";
    assert.equal(getSiteUrl(), "https://staging-students.onrender.com");
    process.env.SITE_URL = "https://students.example.test/";
    assert.equal(getSiteUrl(), "https://students.example.test");
  } finally {
    if (originalSite === undefined) delete process.env.SITE_URL;
    else process.env.SITE_URL = originalSite;
    if (originalRender === undefined) delete process.env.RENDER_EXTERNAL_URL;
    else process.env.RENDER_EXTERNAL_URL = originalRender;
  }
});


test("Google-linked students must complete required Amaris profile fields before dashboard access", () => {
  assert.match(callback, /student_profiles/);
  assert.match(callback, /isStudentProfileComplete\(profile\)/);
  assert.match(callback, /new URL\("\/complete-profile"/);
  assert.match(identity, /linkedProviders\.includes\("google"\)/);
  assert.match(identity, /profileComplete/);
  assert.match(identity, /redirect\([\s\S]*\/complete-profile/);
  assert.match(completeProfile, /completeGoogleProfileAction/);
  assert.match(completeProfile, /name="mobile"/);
  assert.match(completeProfile, /name="province"/);
  assert.match(completeProfile, /name="institution"/);
  assert.match(completeProfile, /name="academicLevel"/);
  assert.match(completeProfile, /name="terms"/);
});

test("Google registration and login preserve their own safe error destinations", () => {
  assert.match(registration, /flow="register"/);
  assert.match(login, /flow="login"/);
  assert.match(button, /name="flow"/);
  assert.match(actions, /flow === "register" \? "\/register" : "\/login"/);
  assert.match(actions, /prompt: "select_account"/);
  assert.match(callback, /searchParams\.get\("flow"\) === "register" \? "register" : "login"/);
});
