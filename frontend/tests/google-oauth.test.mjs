import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const callbackPath = fileURLToPath(new URL("../app/auth/callback/route.ts", import.meta.url));
const loginPath = fileURLToPath(new URL("../app/login/page.tsx", import.meta.url));
const registerPath = fileURLToPath(new URL("../app/register/page.tsx", import.meta.url));
const authPath = fileURLToPath(new URL("../lib/auth.ts", import.meta.url));

const [callbackSource, loginSource, registerSource, authSource] = await Promise.all([
  readFile(callbackPath, "utf8"),
  readFile(loginPath, "utf8"),
  readFile(registerPath, "utf8"),
  readFile(authPath, "utf8"),
]);

test("Google OAuth callback exchanges the PKCE code and verifies the user", () => {
  assert.match(callbackSource, /exchangeCodeForSession\(code\)/);
  assert.match(callbackSource, /supabase\.auth\.getUser\(\)/);
  assert.match(callbackSource, /user\?\.email_confirmed_at/);
  assert.match(callbackSource, /safeRelativePath\(request\.nextUrl\.searchParams\.get\("next"\)\)/);
  assert.match(callbackSource, /new URL\(next, getSiteUrl\(\)\)/);
});

test("student login and registration expose Google authentication", () => {
  assert.match(loginSource, /GoogleAuthButton label="Continue with Google"/);
  assert.match(registerSource, /GoogleAuthButton label="Register with Google"/);
});

test("Google names are supported without using profile metadata for authorization", () => {
  assert.match(authSource, /metadata\.given_name/);
  assert.match(authSource, /metadata\.family_name/);
  assert.match(authSource, /metadata\.full_name/);
  assert.match(authSource, /emailVerified:\s*Boolean\(user\.email_confirmed_at\)/);
});
