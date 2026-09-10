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
