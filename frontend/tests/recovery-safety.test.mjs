import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("safe drafts explicitly exclude secrets and uploads", async () => {
  const source = await readFile(new URL("../components/site/safe-form-draft.tsx", import.meta.url), "utf8");
  assert.match(source, /password\|passcode\|otp\|token\|secret\|card\|cvv\|cvc\|bank\|payment\|signature\|passphrase\|upload\|file/);
  assert.match(source, /sessionStorage/);
  assert.doesNotMatch(source, /localStorage/);
});

test("all requested recovery states are configured", async () => {
  const source = await readFile(new URL("../lib/recovery.ts", import.meta.url), "utf8");
  for (const key of ["400", "403", "404", "429", "500", "502", "503", "payment-pending", "payment-cancelled", "payment-failed", "session-expired", "connection-lost"]) {
    assert.match(source, new RegExp(`\\"${key}\\"\\s*:`), key);
  }
});

test("connection notice is hydration-free, closable, and blocks offline submissions", async () => {
  const source = await readFile(new URL("../components/site/connection-recovery.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /["']use client["']/);
  assert.doesNotMatch(source, /useState|useEffect/);
  assert.match(source, /aria-label="Close connection notice"/);
  assert.match(source, /event\.preventDefault\(\)/);
  assert.match(source, /document\.addEventListener\("submit", preventOfflineSubmission, true\)/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /data-recovery-close/);
  assert.match(source, /window\.addEventListener\("offline", showOffline\)/);
});

test("synthetic browser-test identity is development-only", async () => {
  const authSource = await readFile(new URL("../lib/auth.ts", import.meta.url), "utf8");
  const viteSource = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");

  assert.match(authSource, /__E2E_SYNTHETIC_STUDENT__/);
  assert.match(authSource, /responsive\.student@example\.test/);
  assert.match(viteSource, /process\.env\.NODE_ENV !== "production"/);
  assert.match(viteSource, /process\.env\.E2E_SYNTHETIC_STUDENT === "true"/);
  assert.match(viteSource, /__E2E_SYNTHETIC_STUDENT__:\s*JSON\.stringify\(syntheticE2EStudent\)/);
});
