import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("private student overview authenticates before streaming protected API content", async () => {
  const page = await read("../app/dashboard/page.tsx");
  assert.match(page, /const user = await requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /<StudentDashboardShell/);
  assert.match(page, /<Suspense fallback=\{<StudentDashboardSkeleton \/>\}>/);
  assert.match(page, /async function StudentDashboardContent\(\{/);
  assert.match(page, /getStudentCourses\(\)/);
  assert.match(page, /Promise\.allSettled\(/);
  assert.match(page, /getStudentOrders\(\)/);
  assert.match(page, /getStudentVideoRequests\(\)/);
  assert.match(page, /<StudentWorkflowVisuals/);
  assert.match(page, /id="my-courses"/);
  assert.doesNotMatch(page, /getStaticProps|unstable_cache|force-static|revalidate\s*=/);
});

test("private orders and notifications stream only after verified identity", async () => {
  for (const [path, section, api] of [
    ["../app/dashboard/orders/page.tsx", "Orders", "getStudentOrders"],
    ["../app/dashboard/notifications/page.tsx", "Notifications", "getStudentNotifications"],
  ]) {
    const page = await read(path);
    assert.match(page, /export const dynamic = "force-dynamic"/);
    assert.match(page, /await requireVerifiedStudent/);
    assert.match(page, new RegExp(`<Suspense fallback=\\{<${section}Skeleton \\/>\\}>`));
    assert.match(page, new RegExp(`async function ${section}Content\\(\\{`));
    assert.match(page, new RegExp(`await ${api}\\(\\)`));
    assert.doesNotMatch(page, /getStaticProps|unstable_cache|force-static|revalidate\s*=/);
  }
});

test("tutor timetable is not blocked on verified earnings read", async () => {
  const page = await read("../app/tutor/dashboard/page.tsx");
  assert.match(page, /const pendingEarnings = getTutorEarnings\(\)\.catch\(/);
  assert.match(page, /dashboard = await getTutorDashboard\(\)/);
  assert.match(page, /<Suspense fallback=\{<TutorEarningsSkeleton \/>\}>/);
  assert.match(page, /<TutorEarningsDetails pending=\{pendingEarnings\} \/>/);
  assert.match(page, /<TutorEarningsPanel earnings=\{await pending\} \/>/);
  assert.match(page, /redirect\("\/tutor\/login"\)/);
  assert.match(page, /createTutorSlotAction|updateTutorSlotAction|pauseTutorSlotAction/);
  assert.doesNotMatch(page, /getStaticProps|unstable_cache|force-static/);
});

test("request-local token deduplication never caches student or tutor API responses", async () => {
  const student = await read("../lib/student-api.ts");
  const tutor = await read("../lib/tutor-api.ts");
  for (const api of [student, tutor]) {
    assert.match(api, /import \{ cache \} from "react"/);
    assert.match(api, /cache\(async/);
    assert.match(api, /cache: "no-store"/);
    assert.match(api, /Authorization: `Bearer \$\{token\}`/);
    assert.doesNotMatch(api, /unstable_cache|force-cache|localStorage|sessionStorage/);
  }
  assert.match(student, /requireVerifiedStudent\(\)/);
  assert.match(tutor, /supabase\.auth\.getUser\(\)/);
  assert.match(tutor, /user\.email_confirmed_at/);
  assert.match(tutor, /getTutorDashboard\(\)/);
});
