import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const authPath = fileURLToPath(new URL("../lib/auth.ts", import.meta.url));
const source = await readFile(authPath, "utf8");

test("student identity uses the authoritative Supabase user record", () => {
  assert.match(source, /supabase\.auth\.getUser\(\)/);
  assert.match(source, /emailVerified:\s*Boolean\(user\.email_confirmed_at\)/);
  assert.doesNotMatch(source, /claims\.email_verified/);
});

test("protected student routes still require a verified identity", () => {
  assert.match(source, /if \(!student\)[\s\S]*redirect\(\`\/login\?next=/);
  assert.match(source, /if \(!student\.emailVerified\)[\s\S]*redirect\(\`\/verify-email\?email=/);
});
