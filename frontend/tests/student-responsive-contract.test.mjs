import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return readFile(new URL(path, import.meta.url), "utf8");
}

test("dashboard preserves protected live course data and offers a working section link", async () => {
  const page = await source("../app/dashboard/page.tsx");
  assert.match(page, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /await getStudentCourses\(\)/);
  assert.match(page, /getStudentCourses/);
  assert.match(page, /\[UserRound, "Profile & security", "\/reset-password"\]/);
  assert.match(page, /\[BookOpen, "My courses", "#my-courses"\]/);
  assert.equal((page.match(/id="my-courses"/g) ?? []).length, 2, "both enrolled and empty states must have a course target");
  assert.match(page, /aria-label="Dashboard navigation"/);
  assert.match(page, /aria-current=\{i === 0 \? "page"/);
  assert.match(page, /aria-disabled=\{i !== 0 \? true/);
  assert.match(page, /Course progress is temporarily unavailable/);
});

test("dashboard reflows at small widths, wraps long course names and preserves tap targets", async () => {
  const page = await source("../app/dashboard/page.tsx");
  assert.match(page, /grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-1/);
  assert.match(page, /lg:grid-cols-\[minmax\(0,240px\)_minmax\(0,1fr\)\]/);
  assert.match(page, /sm:grid-cols-2 xl:grid-cols-4/);
  assert.match(page, /min-h-12 min-w-0 items-center/);
  assert.match(page, /\[overflow-wrap:anywhere\]/);
  assert.match(page, /min-w-0 flex-1/);
  assert.match(page, /min-h-12 w-full items-center justify-center/);
  assert.doesNotMatch(page, /overflow-x-hidden/, "do not hide horizontal overflow instead of fixing it");
});

test("protected lesson content fits narrow screens without losing the video, body or save action", async () => {
  const page = await source("../app/learn/[courseSlug]/[lessonSlug]/page.tsx");
  assert.match(page, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /getProtectedLesson\(courseSlug, lessonSlug\)/);
  assert.match(page, /aspect-video w-full min-w-0/);
  assert.match(page, /loading="lazy"/);
  assert.match(page, /\[overflow-wrap:anywhere\]/);
  assert.match(page, /action=\{saveLessonProgressAction\}/);
  assert.match(page, /min-h-12 w-full items-center justify-center/);
});

test("protected checkout wraps references and retains POST redirect to PayFast", async () => {
  const page = await source("../app/checkout/[slug]/page.tsx");
  assert.match(page, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /await createStudentCheckout\(slug\)/);
  assert.match(page, /form method="post" action=\{checkout.gateway_url\}/);
  assert.match(page, /break-all font-mono/);
  assert.match(page, /\[overflow-wrap:anywhere\]/);
  assert.match(page, /min-h-12 w-full/);
});
