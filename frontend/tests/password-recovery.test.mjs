import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({ root, configFile: false, appType: "custom", server: { middlewareMode: true, hmr: false, ws: false } });
const { isPasswordRecoveryCallback, PASSWORD_RECOVERY_COOKIE, PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS } = await vite.ssrLoadModule("/lib/password-recovery.ts");
after(() => vite.close());

const read = rel => readFileSync(new URL(rel, import.meta.url), "utf8");

test("only a real recovery callback with the exact local path can open the reset form", () => {
  assert.equal(isPasswordRecoveryCallback("/reset-password", "password-recovery", null), true);
  assert.equal(isPasswordRecoveryCallback("/reset-password", null, "recovery"), true);
  for (const [next, flow, type] of [
    ["/reset-password", null, "signup"],
    ["/reset-password", null, null],
    ["/reset-password", "normal-signin", "email"],
    ["//attacker.example/reset-password", "password-recovery", null],
    ["https://attacker.example/reset-password", "password-recovery", null],
    ["/dashboard", "password-recovery", null],
  ]) {
    assert.equal(isPasswordRecoveryCallback(next, flow, type), false);
  }
});

test("confirmed reset callback issues 15-minute HttpOnly path-limited recovery proof", () => {
  const callback = read("../app/auth/confirm/route.ts");
  assert.match(callback, /isPasswordRecoveryCallback\(/);
  assert.match(callback, /hasVerifiedAccountEmail\(supabase\.auth\)/);
  assert.match(callback, /if \(recovery\)/);
  assert.match(callback, /httpOnly: true/);
  assert.match(callback, /sameSite: "lax"/);
  assert.match(callback, /path: "\/reset-password"/);
  assert.match(callback, /PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS/);
  assert.equal(PASSWORD_RECOVERY_COOKIE, "amaris-password-recovery");
  assert.match(callback, /issuePasswordRecoveryProof\(/);
  assert.doesNotMatch(callback, /set\(PASSWORD_RECOVERY_COOKIE, "1"/);
  assert.equal(PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS, 900);
});

test("only a verified account with a recovery marker may view or submit new password", () => {
  const page = read("../app/reset-password/page.tsx");
  const actions = read("../app/auth/actions.ts");
  assert.match(page, /get\(PASSWORD_RECOVERY_COOKIE\)/);
  assert.match(page, /getVerifiedRecoveryIdentity\(supabase\.auth\)/);
  assert.match(page, /isValidPasswordRecoveryProof\(/);
  assert.match(actions, /get\(PASSWORD_RECOVERY_COOKIE\)/);
  assert.match(actions, /getVerifiedRecoveryIdentity\(supabase\.auth\)/);
  assert.match(actions, /issuePasswordRecoveryProof\(/);
  assert.match(actions, /isValidPasswordRecoveryProof\(/);
  assert.doesNotMatch(actions, /set\(PASSWORD_RECOVERY_COOKIE, "1"/);
  assert.match(actions, /auth\.updateUser\(\{ password \}\)/);
  assert.match(actions, /auth\.signOut\(\{ scope: "global" \}\)/);
  assert.match(actions, /maxAge: 0/);
});

test("email recovery uses a non-consuming landing and six-digit OTP fallback", () => {
  const codePage = read("../app/reset-password/verify/page.tsx");
  const template = read("../email-templates/recovery.html");
  const actions = read("../app/auth/actions.ts");
  assert.match(codePage, /verifyRecoveryCodeAction/);
  assert.match(codePage, /Continue to choose a new password/);
  assert.match(codePage, /Six-digit recovery code/);
  assert.ok(template.includes("{{ .Token }}"));
  assert.ok(template.includes("{{ .TokenHash }}"));
  assert.ok(template.includes("{{ .SiteURL }}/reset-password/verify?token_hash={{ .TokenHash }}"));
  assert.ok(!template.includes("{{ .RedirectTo }}"));
  assert.doesNotMatch(template, /localhost/i);
  assert.ok(!template.includes("{{ .ConfirmationURL }}"));
  assert.ok(actions.includes('type: "recovery"'));
  assert.ok(actions.includes("recoveryCookies.set(PASSWORD_RECOVERY_COOKIE"));
  assert.ok(read("../proxy.ts").includes('"/reset-password/:path*"'));
});

test("all account portals reuse recovery instead of separate role-specific password stores", () => {
  const student = read("../app/login/page.tsx");
  const tutor = read("../app/tutor/login/page.tsx");
  const applicant = read("../app/tutor/apply/login/page.tsx");
  const recovery = read("../app/forgot-password/page.tsx");
  const verify = read("../app/reset-password/verify/page.tsx");
  const reset = read("../app/reset-password/page.tsx");
  const actions = read("../app/auth/actions.ts");
  for (const portal of [student, tutor, applicant]) {
    assert.match(portal, /href="\/forgot-password"/);
  }
  for (const label of ["student", "tutor", "tutor applicant", "other registered"]) {
    assert.match(recovery.toLowerCase(), new RegExp(label));
  }
  assert.match(recovery, /href="\/tutor\/login"/);
  assert.match(recovery, /href="\/tutor\/apply\/login"/);
  assert.match(verify, /six-digit code/);
  assert.match(reset, /get\(PASSWORD_RECOVERY_COOKIE\)/);
  assert.match(actions, /auth\.resetPasswordForEmail\(email/);
  assert.match(actions, /auth\.verifyOtp\(\{ email, token, type: "recovery" \}\)/);
  assert.match(actions, /user\?\.email_confirmed_at/);
  assert.match(actions, /auth\.updateUser\(\{ password \}\)/);
  assert.match(actions, /auth\.signOut\(\{ scope: "global" \}\)/);
});

test("forgot password is available from student and tutor login without disclosing accounts", () => {
  const student = read("../app/login/page.tsx");
  const tutor = read("../app/tutor/login/page.tsx");
  const form = read("../app/forgot-password/page.tsx");
  assert.match(student, /href="\/forgot-password"/);
  assert.match(tutor, /href="\/forgot-password"/);
  assert.match(form, /forgotPasswordAction/);
  assert.match(form, /type="email"/);
  assert.match(form, /sent/);
});
