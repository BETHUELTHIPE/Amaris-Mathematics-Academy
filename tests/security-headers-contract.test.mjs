import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const workerSource = fs.readFileSync(path.join(process.cwd(), "worker/index.ts"), "utf8");

test("worker applies browser security headers to every response", () => {
  for (const header of [
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
  ]) {
    assert.ok(workerSource.includes(`"${header}"`), `missing ${header}`);
  }
  assert.match(workerSource, /frame-ancestors 'none'/);
  assert.match(workerSource, /object-src 'none'/);
});

test("protected responses are private and never cached", () => {
  for (const pathPrefix of ["/dashboard", "/documents", "/checkout", "/api/auth-state"]) {
    assert.ok(workerSource.includes(`"${pathPrefix}"`), `missing protected prefix ${pathPrefix}`);
  }
  assert.match(workerSource, /private, no-store, max-age=0/);
  assert.match(workerSource, /Vary/);
  assert.match(workerSource, /Cookie/);
});
