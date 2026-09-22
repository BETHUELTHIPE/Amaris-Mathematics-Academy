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


test("synthetic E2E auth bypass is compile-time only and disabled in production Nitro", async () => {
  const { readFile } = await import("node:fs/promises");
  const proxySource = await readFile(new URL("../lib/supabase/proxy.ts", import.meta.url), "utf8");
  const devViteSource = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  const prodViteSource = await readFile(new URL("../vite.node.config.ts", import.meta.url), "utf8");

  assert.match(proxySource, /protectedPath && __E2E_SYNTHETIC_STUDENT__/);
  assert.match(devViteSource, /process\.env\.NODE_ENV !== "production" && process\.env\.E2E_SYNTHETIC_STUDENT === "true"/);
  assert.match(prodViteSource, /__E2E_SYNTHETIC_STUDENT__:\s*JSON\.stringify\(false\)/);
});
