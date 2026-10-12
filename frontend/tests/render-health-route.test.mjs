import assert from "node:assert/strict";
import test from "node:test";
import { GET } from "../app/health/ready/route.ts";

test("the readiness route configured on Render returns private JSON", async () => {
  const response = await GET();
  assert.equal(response.status, 200);
  assert.equal((await response.json()).status, "ok");
  assert.match(response.headers.get("Cache-Control"), /no-store/);
});
