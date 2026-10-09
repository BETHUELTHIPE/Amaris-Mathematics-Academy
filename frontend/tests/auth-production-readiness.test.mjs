import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const authSource = fs.readFileSync(path.join(process.cwd(), "lib/auth.ts"), "utf8");
const actionsSource = fs.readFileSync(path.join(process.cwd(), "app/auth/actions.ts"), "utf8");
const authStateSource = fs.readFileSync(path.join(process.cwd(), "app/api/auth-state/route.ts"), "utf8");
const registerSource = fs.readFileSync(path.join(process.cwd(), "app/register/page.tsx"), "utf8");

test("protected student identity verifies both JWT claims and the authoritative Supabase user", () => {
  assert.match(authSource, /supabase\.auth\.getClaims\(\)/);
  assert.match(authSource, /supabase\.auth\.getUser\(\)/);
  assert.match(authSource, /userData\.user\.id !== data\.claims\.sub/);
  assert.match(authSource, /Boolean\(userData\.user\.email_confirmed_at\)/);
  assert.doesNotMatch(authSource, /claims\.email_verified/);
});

test("unverified and anonymous identities cannot enter protected student pages", () => {
  assert.match(authSource, /if \(!student\)/);
  assert.match(authSource, /redirect\(\`\/login\?next=/);
  assert.match(authSource, /if \(!student\.emailVerified\)/);
  assert.match(authSource, /redirect\(\`\/verify-email\?email=/);
});

test("redirect targets are constrained to same-site relative paths", () => {
  assert.match(authSource, /!value\.startsWith\("\/"\)/);
  assert.match(authSource, /value\.startsWith\("\/\/"\)/);
  assert.match(authSource, /url\.origin !== "https:\/\/app\.local"/);
  assert.match(authSource, /url\.pathname\.startsWith\("\/auth\/"\)/);
});

test("public registration cannot request privileged application roles", () => {
  assert.doesNotMatch(actionsSource, /formData\.get\("role"\)/);
  assert.doesNotMatch(actionsSource, /requested_role|privileged_role_approved/);
  assert.doesNotMatch(registerSource, /name="role"/);
});

test("password authentication avoids enumeration and recovery revokes sessions", () => {
  assert.match(actionsSource, /The email or password is incorrect\. Please try again\./);
  assert.match(actionsSource, /resetPasswordForEmail\(/);
  assert.match(actionsSource, /supabase\.auth\.getUser\(\)/);
  assert.match(actionsSource, /supabase\.auth\.signOut\(\{ scope: "global" \}\)/);
});

test("auth-state responses are private and never cache shared session state", () => {
  assert.match(authStateSource, /"Cache-Control": "private, no-store, max-age=0"/);
  assert.match(authStateSource, /Vary: "Cookie"/);
});
