import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (relativePath) =>
  fs.readFileSync(path.join(process.cwd(), relativePath), "utf8");

const cmsSource = read("lib/cms.ts");
const coursePageSource = read("app/courses/[slug]/page.tsx");
const deferredAuthSource = read("components/site/deferred-auth-controls.tsx");
const authControlsSource = read("components/site/auth-controls.tsx");

test("public course details do not require request-time authentication SSR", () => {
  assert.doesNotMatch(
    coursePageSource,
    /getStudentIdentity|force-dynamic/,
    "public course detail pages must stay free of request-time auth SSR",
  );
  assert.match(
    coursePageSource,
    /href="\/dashboard"/,
    "course enrollment must still flow through the protected dashboard",
  );
});

test("managed CMS reads use persistent fetch caching and render deduplication", () => {
  assert.match(cmsSource, /cache:\s*"force-cache"/);
  assert.match(cmsSource, /next:\s*\{\s*revalidate:\s*60\s*\}/);
  assert.match(cmsSource, /export const getManagedCourses = cache\(/);
  assert.match(cmsSource, /export const getManagedCourse = cache\(/);
});

test("deferred authentication reuses the first auth-state response", () => {
  assert.match(deferredAuthSource, /emailVerified\?: boolean/);
  assert.match(deferredAuthSource, /initialState=\{authState\}/);
  assert.match(authControlsSource, /initialState = "loading"/);
  assert.match(
    authControlsSource,
    /if \(initialState !== "loading"\) return;/,
    "lazy auth controls must not issue a second auth-state request when state is already known",
  );
});
