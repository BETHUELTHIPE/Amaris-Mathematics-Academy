import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("exposes the readiness route configured on the live Render service", async () => {
  const source = await readFile(
    new URL("../app/health/ready/route.ts", import.meta.url),
    "utf8",
  );

  assert.match(source, /export async function GET/);
  assert.match(source, /status:\\s*"ok"/);
  assert.match(source, /status:\\s*200/);
  assert.match(source, /Cache-Control/);
  assert.match(source, /no-store/);
});
