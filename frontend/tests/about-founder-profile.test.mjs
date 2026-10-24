import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const about = await readFile(new URL("../app/about/page.tsx", import.meta.url), "utf8");
const profile = await readFile(new URL("../components/site/about-founder-profile.tsx", import.meta.url), "utf8");

test("About page keeps founder details and accessible education and technology sections", () => {
  assert.match(about, /FounderProfile/);
  assert.match(about, /founder-bethuel-moukangwe\.jpg/);
  for (const anchor of ["founder-qualifications", "founder-experience", "academy-technology"]) {
    assert.match(profile, new RegExp('id="' + anchor + '"'));
    assert.match(profile, new RegExp('aria-labelledby="' + anchor + '-title"'));
  }
});

test("academic credentials distinguish complete degrees from partial studies", () => {
  assert.match(profile, /University of South Africa \(UNISA\)/);
  assert.match(profile, /Completed November 2019/);
  assert.match(profile, /EXPLOREAI Academy, South Africa/);
  assert.match(profile, /16 January – 30 July 2023/);
  assert.match(profile, /2007 · Partially completed/);
  assert.match(profile, /the degree was not completed/);
});

test("About page accurately represents the Amaris platform technology", () => {
  for (const technology of ["Next.js", "TypeScript", "Django REST Framework", "Supabase", "Docker", "Render", "Celery", "PayFast", "Grafana", "Prometheus"]) {
    assert.ok(profile.includes(technology), "Missing platform technology: " + technology);
  }
  assert.match(profile, /in development or staging verification/);
});
