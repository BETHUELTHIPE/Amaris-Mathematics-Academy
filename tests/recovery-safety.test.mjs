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

test("connection notice can be closed and blocks offline submissions", async () => {
  const source = await readFile(new URL("../components/site/connection-recovery.tsx", import.meta.url), "utf8");
  assert.match(source, /onClick=\{\(\) => setDismissed\(true\)\}/);
  assert.match(source, /aria-label="Close connection notice"/);
  assert.match(source, /event\.preventDefault\(\)/);
  assert.match(source, /document\.addEventListener\("submit", preventOfflineSubmission, true\)/);
  assert.match(source, /event\.key === "Escape"/);
});
