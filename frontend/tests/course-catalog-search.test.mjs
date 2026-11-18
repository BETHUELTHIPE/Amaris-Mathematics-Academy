import assert from "node:assert/strict";
import test from "node:test";
import { catalogueApiPath, catalogueHref, normalizeCatalogOptions } from "../lib/course-catalog-search.mjs";

test("search normalizes query, programmes, sort and bounded page numbers", () => {
  assert.deepEqual(normalizeCatalogOptions({ query: "  maths   matric  ", programme: "ieb", level: "Grade 12", sort: "price", page: "2" }), {
    query: "maths matric", programme: "IEB", level: "Grade 12", sort: "price", page: 2, validationError: "",
  });
  for (const page of ["0", "-1", "2.2", "100001", "Infinity", ["2"], "x"]) assert.equal(normalizeCatalogOptions({ page }).page, 1);
  assert.equal(normalizeCatalogOptions({ query: ["private"], programme: "admin", sort: "password" }).query, "");
  assert.equal(normalizeCatalogOptions({ sort: "password" }).sort, "relevance");
});

test("pagination links preserve all selected filters and sort", () => {
  const href = catalogueHref({ query: "calculus", programme: "IEB", level: "Grade 12", sort: "-price", page: 4 });
  const url = new URL(href, "https://academy.example");
  assert.equal(url.pathname, "/courses");
  assert.deepEqual(Object.fromEntries(url.searchParams), { q: "calculus", programme: "IEB", level: "Grade 12", sort: "-price", page: "4" });
  assert.equal(catalogueHref(), "/courses");
});

test("API search covers the server catalogue with bounded response size", () => {
  const url = new URL(catalogueApiPath({ query: "Grade 12 calculus", programme: "CAPS", level: "Grade 12", sort: "price", page: 2 }), "https://cms.example");
  assert.equal(url.pathname, "/courses/");
  assert.deepEqual(Object.fromEntries(url.searchParams), { page: "2", page_size: "24", search: "Grade 12 calculus", programme: "CAPS", academic_level: "Grade 12", ordering: "price" });
});

test("queries cannot inject another parameter or an off-site link", () => {
  const url = new URL(catalogueHref({ query: "x&programme=admin", level: "Grade 12&ordering=private" }), "https://academy.example");
  assert.equal(url.origin, "https://academy.example");
  assert.equal(url.searchParams.get("q"), "x&programme=admin");
  assert.equal(url.searchParams.get("programme"), null);
  assert.equal(url.searchParams.get("level"), "Grade 12&ordering=private");
  assert.equal(normalizeCatalogOptions({ query: "x".repeat(1000) }).query.length, 100);
});

test("validation distinguishes malformed search from service unavailability", () => {
  assert.ok(normalizeCatalogOptions({ query: "!!!" }).validationError);
  assert.ok(normalizeCatalogOptions({ query: "one two three four five six seven eight nine" }).validationError);
  assert.equal(normalizeCatalogOptions({ query: "Gr.12 maths NC(V)" }).validationError, "");
});
