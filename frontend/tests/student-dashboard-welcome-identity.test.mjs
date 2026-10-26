import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("private overview greets verified students by full registered name and signed-in email", async () => {
  const page = await read("../app/dashboard/page.tsx");
  assert.match(page, /const user = await requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(page, /const fullName = user\.displayName\.trim\(\)/);
  assert.match(page, /const signedInEmail = user\.email/);
  assert.match(page, /title=\{\x60Welcome, \$\{fullName\}\.\x60\}/);
  assert.match(page, /description=\{\x60Signed in as \$\{signedInEmail\}/);
  assert.doesNotMatch(page, /title=\{\x60Welcome, \$\{firstName\}/);
  assert.match(page, /export const dynamic = "force-dynamic"/);
  assert.match(page, /robots: \{ index: false, follow: false \}/);
});

test("full name and email come from the authenticated Supabase user record, never URL parameters", async () => {
  const auth = await read("../lib/auth.ts");
  const page = await read("../app/dashboard/page.tsx");
  assert.match(auth, /await supabase\.auth\.getUser\(\)/);
  assert.match(auth, /userData\.user\.id !== data\.claims\.sub/);
  assert.match(auth, /mapClaims\(data\.claims, userData\.user\)/);
  assert.match(auth, /authUser\.user_metadata/);
  assert.match(auth, /authUser\.email\.trim\(\)\.toLowerCase\(\)/);
  assert.match(auth, /emailVerified: Boolean\(authUser\.email_confirmed_at\)/);
  assert.match(auth, /firstName,\s*lastName,\s*displayName: \[firstName, lastName\]\.filter\(Boolean\)\.join\(" "\)/);
  assert.doesNotMatch(page, /searchParams\.email|searchParams\.fullName|localStorage|sessionStorage/);
});

test("welcome identity stays server-rendered inside the authenticated private dashboard shell", async () => {
  const page = await read("../app/dashboard/page.tsx");
  const shell = await read("../components/site/student-dashboard-shell.tsx");
  assert.match(page, /<StudentDashboardShell/);
  assert.match(shell, /\{title\}/);
  assert.match(shell, /\{description\}/);
  assert.match(page, /<Suspense fallback=\{<StudentDashboardSkeleton \/>\}>/);
  assert.doesNotMatch(shell, /fetch\(|useEffect|localStorage/);
});
