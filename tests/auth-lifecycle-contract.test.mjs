import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const actionsSource = fs.readFileSync(path.join(process.cwd(), "app/auth/actions.ts"), "utf8");
const authSource = fs.readFileSync(path.join(process.cwd(), "lib/auth.ts"), "utf8");

function expectSource(pattern, message) {
  assert.match(actionsSource, pattern, message);
}

test("registration enforces strong passwords and matching confirmation", () => {
  expectSource(/\.min\(12, "Use at least 12 characters for your password\."\)/, "minimum password length is required");
  expectSource(/\.max\(72, "Your password must be 72 characters or fewer\."\)/, "maximum password length is required");
  expectSource(/\.regex\(\/\[a-z\]\//, "lowercase requirement is required");
  expectSource(/\.regex\(\/\[A-Z\]\//, "uppercase requirement is required");
  expectSource(/\.regex\(\/\[0-9\]\//, "number requirement is required");
  expectSource(/\.regex\(\/\[\^A-Za-z0-9\]\//, "symbol requirement is required");
  expectSource(/values\.password === values\.confirmPassword/, "password confirmation must match");
});

test("registration delegates credential storage to Supabase Auth and normalizes email", () => {
  expectSource(/\.trim\(\)\.toLowerCase\(\)\.email\(\)/, "email should be normalized and validated");
  expectSource(/supabase\.auth\.signUp\(/, "registration should use Supabase Auth");
  assert.doesNotMatch(actionsSource, /password\s*:\s*values\.password[\s\S]*studentProfiles/,
    "plaintext passwords must not be written to the profile mirror");
});

test("email verification requires a six-digit OTP and uses signup verification", () => {
  expectSource(/\^\\d\{6\}\$\/.test\(token\)/, "verification token must be six digits");
  expectSource(/supabase\.auth\.verifyOtp\(\{[\s\S]*type:\s*"signup"/, "signup OTP verification must be used");
  expectSource(/invalid or has expired/, "invalid or expired verification must have a safe failure path");
});

test("unverified students cannot enter protected areas", () => {
  assert.match(authSource, /if \(!student\.emailVerified\)/);
  assert.match(authSource, /redirect\(`\/verify-email\?email=/);
});

test("resend verification and login respect provider throttling", () => {
  const rateLimitChecks = actionsSource.match(/rate limit\|too many/g) ?? [];
  assert.ok(rateLimitChecks.length >= 3, "registration, resend, and login should all handle provider rate limiting");
  expectSource(/resend\(\{[\s\S]*type:\s*"signup"/, "resend must use signup verification flow");
});

test("login uses a generic error to reduce account-enumeration risk", () => {
  expectSource(/The email or password is incorrect\. Please try again\./, "login failures must be generic");
  assert.doesNotMatch(actionsSource, /no account exists|email not found|user not found/i);
});

test("forgot-password response is enumeration safe", () => {
  expectSource(/resetPasswordForEmail\(/, "password reset must be delegated to Supabase Auth");
  expectSource(/The same response is shown whether the account exists or not\./,
    "reset flow should explicitly preserve account-enumeration safety");
  expectSource(/redirect\("\/forgot-password\?sent=1"\)/,
    "reset request should return the same success state regardless of account existence");
});

test("reset requires an authenticated recovery session, updates password, then revokes sessions globally", () => {
  expectSource(/supabase\.auth\.getUser\(\)/, "reset must require a valid recovery session");
  expectSource(/That reset link has expired\. Request a new one\./, "expired reset sessions must be rejected");
  expectSource(/supabase\.auth\.updateUser\(\{ password \}\)/, "password must be changed through Supabase Auth");
  expectSource(/supabase\.auth\.signOut\(\{ scope: "global" \}\)/, "password reset must revoke existing sessions");
});

test("logout invalidates the local session", () => {
  expectSource(/supabase\.auth\.signOut\(\{ scope: "local" \}\)/, "logout should invalidate the current local session");
});

test("auth redirects are constrained to safe relative paths", () => {
  assert.match(authSource, /safeRelativePath/);
  assert.match(authSource, /value\.startsWith\("\/\/"\)/);
  assert.match(authSource, /url\.origin !== "https:\/\/app\.local"/);
});
