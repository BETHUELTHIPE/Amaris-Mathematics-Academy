import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function source(relativePath) {
  return fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const navigation = source("../components/dashboard/student-navigation.tsx");
const routes = [
  ["../app/dashboard/page.tsx", "/dashboard"],
  ["../app/dashboard/courses/page.tsx", "/dashboard/courses"],
  ["../app/dashboard/orders/page.tsx", "/dashboard/orders"],
  ["../app/dashboard/notifications/page.tsx", "/dashboard/notifications"],
  ["../app/dashboard/profile/page.tsx", "/dashboard/profile"],
];

test("every student dashboard section has a real accessible link and page", () => {
  for (const [file, path] of routes) {
    assert.match(navigation, new RegExp(path.replaceAll("/", "\\/"), "g"));
    assert.match(source(file), /requireVerifiedStudent\(/);
    assert.ok(source(file).includes(`currentPath="${path}"`));
  }
  assert.match(navigation, /aria-current=\{active \? "page" : undefined\}/);
  assert.match(navigation, /<Link/);
  assert.doesNotMatch(navigation, /href="\/reset-password"/);
});

test("student orders use a private read-only backend endpoint and sanitized payload", () => {
  const api = source("../lib/student-api.ts");
  const backend = source("../../backend/content/student_views.py");
  const urls = source("../../backend/content/urls.py");
  assert.match(api, /studentFetch<\{ orders: StudentOrder\[\] \}>\("\/student\/orders\/"\)/);
  assert.match(backend, /class StudentOrdersView\(StudentAPIView\)/);
  assert.match(backend, /filter\(student=student\)/);
  assert.match(backend, /Cache-Control/);
  assert.match(urls, /"student\/orders\/"/);
  assert.doesNotMatch(backend.slice(backend.indexOf("class StudentOrdersView"), backend.indexOf("class StudentLessonView")), /raw_response|provider_reference|zoom_join_url/);
});

test("dashboard sections show explicit errors instead of pretending no purchases exist", () => {
  assert.match(source("../app/dashboard/courses/page.tsx"), /!available/);
  assert.match(source("../app/dashboard/orders/page.tsx"), /!available/);
  assert.match(source("../app/dashboard/notifications/page.tsx"), /!available/);
  assert.match(source("../app/dashboard/profile/page.tsx"), /\/forgot-password/);
});
