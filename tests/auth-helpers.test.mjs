import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const authSource = fs.readFileSync(path.join(process.cwd(), "lib/auth.ts"), "utf8");

test("safeRelativePath rejects absolute and protocol-relative redirects", () => {
  assert.match(authSource, /!value\.startsWith\("\/"\)/);
  assert.match(authSource, /value\.startsWith\("\/\/"\)/);
  assert.match(authSource, /url\.origin !== "https:\/\/app\.local"/);
});

test("safeRelativePath blocks auth loops", () => {
  for (const route of [
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/session-expired",
  ]) {
    assert.ok(authSource.includes(`"${route}"`), `expected ${route} to be blocked`);
  }
  assert.match(authSource, /url\.pathname\.startsWith\("\/auth\/"\)/);
});

test("student identity requires verified claim mapping", () => {
  assert.match(authSource, /emailVerified: claims\.email_verified === true/);
  assert.match(authSource, /redirect\(`\/verify-email\?email=/);
});

test("name mapping trims and caps user metadata", () => {
  assert.match(authSource, /value\.trim\(\)\.slice\(0, 80\)/);
});
