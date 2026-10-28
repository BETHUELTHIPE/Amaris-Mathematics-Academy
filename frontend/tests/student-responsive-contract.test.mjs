import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return readFile(new URL(path, import.meta.url), "utf8");
}

test("dashboard preserves protected live course data and offers a working section link", async () => {
  const page = await source("../app/dashboard/page.tsx");
  const navigation = await source("../components/site/dashboard-navigation.tsx");
  const shell = await source("../components/site/student-dashboard-shell.tsx");
  assert.match(page, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /await getStudentCourses\(\)/);
  assert.match(page, /getStudentCourses/);
  assert.match(navigation, /label: "Profile & security", href: "\/reset-password"/);
  assert.match(navigation, /label: "My courses", href: "\/dashboard#my-courses"/);
  assert.match(navigation, /label: "Orders & payments", href: "\/dashboard\/orders"/);
  assert.match(navigation, /label: "Notifications", href: "\/dashboard\/notifications"/);
  assert.equal((page.match(/id="my-courses"/g) ?? []).length, 2, "both enrolled and empty states must have a course target");
  assert.match(shell, /<DashboardNavigation active=\{active\}/);
  assert.match(navigation, /aria-label="Dashboard navigation"/);
  assert.match(navigation, /aria-current=\{isActive \? "page"/);
  assert.doesNotMatch(navigation, /aria-disabled/);
  assert.match(page, /Course progress is temporarily unavailable/);
});

test("dashboard reflows at small widths, wraps long course names and preserves tap targets", async () => {
  const page = await source("../app/dashboard/page.tsx");
  const navigation = await source("../components/site/dashboard-navigation.tsx");
  const shell = await source("../components/site/student-dashboard-shell.tsx");
  assert.match(navigation, /grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-1/);
  assert.match(shell, /lg:grid-cols-\[minmax\(0,240px\)_minmax\(0,1fr\)\]/);
  assert.match(page, /sm:grid-cols-2 xl:grid-cols-4/);
  assert.match(navigation, /min-h-12 min-w-0 items-center/);
  assert.match(shell, /\[overflow-wrap:anywhere\]/);
  assert.match(shell, /min-w-0 flex-1/);
  assert.match(page, /min-h-12 w-full items-center justify-center/);
  assert.doesNotMatch(`${page}${navigation}${shell}`, /overflow-x-hidden/, "do not hide horizontal overflow instead of fixing it");
});

test("orders and notifications are protected, responsive and backed by private student APIs", async () => {
  const orders = await source("../app/dashboard/orders/page.tsx");
  const notifications = await source("../app/dashboard/notifications/page.tsx");
  const api = await source("../lib/student-api.ts");
  const invoiceRoute = await source("../app/dashboard/orders/invoice/route.ts");
  assert.match(orders, /requireVerifiedStudent\("\/dashboard\/orders"\)/);
  assert.match(orders, /await getStudentOrders\(\)/);
  assert.match(orders, /sm:grid-cols-3/);
  assert.match(orders, /min-h-12 w-full items-center justify-center/);
  assert.match(notifications, /requireVerifiedStudent\("\/dashboard\/notifications"\)/);
  assert.match(notifications, /await getStudentNotifications\(\)/);
  assert.match(notifications, /\[overflow-wrap:anywhere\]/);
  assert.match(api, /studentFetch<StudentOrder\[]>\("\/student\/orders\/"\)/);
  assert.match(api, /studentFetch<StudentNotification\[]>\("\/student\/notifications\/"\)/);
  assert.match(invoiceRoute, /downloadStudentCourseInvoice\(reference\)/);
  assert.match(invoiceRoute, /"Cache-Control": "private, no-store"/);
  assert.doesNotMatch(`${orders}${notifications}`, /overflow-x-hidden/);
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
  assert.match(page, /PayFastHostedCheckout/);
  assert.match(page, /break-all font-mono/);
  assert.match(page, /\[overflow-wrap:anywhere\]/);
  const form = await source("../components/site/payfast-hosted-checkout.tsx");
  assert.match(form, /min-h-12 w-full/);
});
