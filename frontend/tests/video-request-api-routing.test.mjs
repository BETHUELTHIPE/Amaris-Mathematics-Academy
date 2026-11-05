import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { normalizeCmsApiBaseUrl } from "../lib/cms-api-url.ts";

test("Django CMS origin is normalized to the live /api/v1 endpoint", () => {
  assert.equal(
    normalizeCmsApiBaseUrl("https://amaris-production-web.onrender.com"),
    "https://amaris-production-web.onrender.com/api/v1",
  );
  assert.equal(
    normalizeCmsApiBaseUrl("https://amaris-production-web.onrender.com/api/v1/"),
    "https://amaris-production-web.onrender.com/api/v1",
  );
  assert.equal(
    normalizeCmsApiBaseUrl("http://127.0.0.1:8000/"),
    "http://127.0.0.1:8000/api/v1",
  );
});

test("invalid CMS bases fail closed instead of sending requests to a 404 or external URL", () => {
  for (const value of [
    "ftp://cms.example.test",
    "https://cms.example.test/api",
    "https://cms.example.test/student",
    "https://example.test/api/v1?token=dummy",
    "https://user:password@example.test",
  ]) {
    assert.throws(() => normalizeCmsApiBaseUrl(value));
  }
});

test("video checkout and package pricing both use the same normalized API prefix", async () => {
  const api = await readFile(new URL("../lib/student-api.ts", import.meta.url), "utf8");
  const packages = await readFile(new URL("../lib/video-requests.ts", import.meta.url), "utf8");
  const backendUrls = await readFile(
    new URL("../../backend/content/urls.py", import.meta.url),
    "utf8",
  );
  assert.match(api, /return normalizeCmsApiBaseUrl\(base\)/);
  assert.match(api, /\/student\/video-requests\/checkout\//);
  assert.match(packages, /normalizeCmsApiBaseUrl\(configuredBaseUrl\)/);
  assert.match(packages, /\/video-requests\/packages\//);
  assert.match(backendUrls, /path\("student\/video-requests\/checkout\/"/);
  assert.match(backendUrls, /path\("video-requests\/packages\/"/);
});
