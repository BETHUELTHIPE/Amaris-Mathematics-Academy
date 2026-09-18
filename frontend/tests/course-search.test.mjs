import assert from "node:assert/strict";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  appType: "custom",
  configFile: false,
  root,
  resolve: { alias: { "@": root } },
  server: { middlewareMode: true },
});

after(async () => {
  await vite.close();
});

const [{ courseMatchesSearch }, { courses }] = await Promise.all([
  vite.ssrLoadModule("/lib/course-search.ts"),
  vite.ssrLoadModule("/lib/courses.ts"),
]);

function slugs(query, filter = "All") {
  return courses
    .filter((course) => courseMatchesSearch(course, query, filter))
    .map((course) => course.slug);
}

test("finds TVET N4 by level and curriculum language", () => {
  assert.deepEqual(slugs("TVET N4"), ["tvet-engineering-mathematics-n4"]);
});

test("finds linear algebra by module terminology", () => {
  assert.deepEqual(slugs("linear systems"), ["linear-algebra-essentials"]);
});

test("finds calculus by title and module concepts", () => {
  const results = slugs("calculus derivatives");
  assert.equal(results[0], "university-calculus-foundations");
  assert.ok(results.includes("university-calculus-foundations"));
});

test("combines text relevance with curriculum filters", () => {
  assert.deepEqual(slugs("algebra", "TVET"), ["tvet-engineering-mathematics-n4"]);
  assert.ok(slugs("Grade 12", "CAPS").includes("caps-grade-12-mathematics"));
});
