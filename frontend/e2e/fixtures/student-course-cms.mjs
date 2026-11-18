import { createServer } from "node:http";

// Development-only fixture, bound to loopback. No production inventory or PII.
const course = {
  slug: "caps-grade-12-mathematics",
  title: "CAPS Grade 12 Mathematics",
  curriculum: "CAPS",
  academic_level: "Grade 12",
  price: "250.00",
  short_description: "Synthetic maths class for browser verification.",
  estimated_hours: 1,
  featured: true,
  lesson_count: 1,
  modules: [{ title: "Algebra & equations" }],
};

const endpoints = new Map([
  ["/health", { ready: true }],
  ["/api/v1/bootstrap/", { settings: null, navigation: [] }],
  ["/api/v1/announcements/", []],
  ["/api/v1/courses/featured/", [course]],
  ["/api/v1/courses/", { count: 1, next: null, previous: null, results: [course] }],
  [`/api/v1/courses/${course.slug}/`, course],
]);

createServer((request, response) => {
  const path = new URL(request.url, "http://127.0.0.1").pathname;
  const data = request.method === "GET" ? endpoints.get(path) : undefined;
  response.writeHead(data === undefined ? 404 : 200, { "Content-Type": "application/json" });
  response.end(JSON.stringify(data ?? { detail: "Not found" }));
}).listen(3001, "127.0.0.1");
