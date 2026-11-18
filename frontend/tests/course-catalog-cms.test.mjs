import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);

// Compile the real CMS client with its real local helpers. All outbound fetches
// are supplied by each test; no test contacts a live backend or student account.
function cmsClient(fetch, configuredUrl = "https://cms.example") {
  const modules = new Map();
  const process = { env: configuredUrl === null ? {} : { CMS_API_URL: configuredUrl } };
  function load(filename) {
    if (modules.has(filename)) return modules.get(filename).exports;
    const loadedModule = { exports: {} };
    modules.set(filename, loadedModule);
    const code = ts.transpileModule(readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText;
    const localRequire = (id) => {
      if (!id.startsWith("@/")) return require(id);
      const target = path.join(frontend, id.slice(2));
      return load(path.extname(target) ? target : `${target}.ts`);
    };
    runInNewContext(code, { module: loadedModule, exports: loadedModule.exports, require: localRequire, process, fetch, URL, URLSearchParams, AbortSignal, console }, { filename });
    return loadedModule.exports;
  }
  return load(path.join(frontend, "lib/cms.ts"));
}

test("real CMS client maps every filter to one bounded full-catalogue API request", async () => {
  let requested;
  const cms = cmsClient(async url => { requested = String(url); return Response.json({ count: 0, results: [], next: null, previous: null }); });
  const result = await cms.getManagedCourseCatalog({ query: "calculus", programme: "IEB", level: "Grade 12", sort: "price", page: 2 });
  const url = new URL(requested);
  assert.equal(url.pathname, "/api/v1/courses/");
  assert.deepEqual(Object.fromEntries(url.searchParams), { page: "2", page_size: "24", search: "calculus", programme: "IEB", academic_level: "Grade 12", ordering: "price" });
  assert.equal(result.available, true);
});

test("a genuine zero-result response never becomes sample inventory", async () => {
  const cms = cmsClient(async () => Response.json({ count: 0, results: [], next: null, previous: null }));
  const result = await cms.getManagedCourseCatalog();
  assert.equal(result.available, true);
  assert.equal(result.count, 0);
  assert.equal(result.courses.length, 0);
});

test("CMS failure is an unavailable state, not sample inventory", async () => {
  const cms = cmsClient(async () => new Response("Unavailable", { status: 503 }));
  const result = await cms.getManagedCourseCatalog();
  assert.equal(result.available, false);
  assert.equal(result.courses.length, 0);
});

test("a configured CMS cannot fall back to a sample course after a 404", async () => {
  const cms = cmsClient(async () => new Response("Not found", { status: 404 }));
  assert.equal(await cms.getManagedCourse("caps-grade-12-mathematics"), undefined);
});

test("invalid search is explained without making an API request", async () => {
  let calls = 0;
  const cms = cmsClient(async () => { calls++; throw new Error("Must not fetch"); });
  const result = await cms.getManagedCourseCatalog({ query: "!!!" });
  assert.ok(result.validationError);
  assert.equal(calls, 0);
});

test("missing CMS configuration does not advertise local sample courses", async () => {
  let calls = 0;
  const cms = cmsClient(async () => { calls++; throw new Error("Must not fetch"); }, null);
  // Explicitly invalid configuration is also fail-closed.
  const invalid = cmsClient(async () => { throw new Error("Must not fetch"); }, "not-a-url");
  assert.equal((await invalid.getManagedCourseCatalog()).available, false);
  assert.equal((await cms.getManagedCourseCatalog()).available, false);
  assert.equal(calls, 0);
});

test("homepage featured products use their dedicated bounded endpoint", async () => {
  let requested;
  const cms = cmsClient(async url => { requested = String(url); return Response.json([]); }, "https://cms.example/api/v1/");
  await cms.getManagedFeaturedCourses();
  assert.equal(new URL(requested).pathname, "/api/v1/courses/featured/");
});
