import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const mockModule = `
export const state = {};
export function getSiteUrl() { return "https://academy.example.test"; }
export function safeRelativePath(path) { return path || "/dashboard"; }
export async function createSupabaseServerClient() {
  if (state.unavailable) throw new Error("private configuration details");
  return { auth: {
    signUp: async (input) => { state.signup = input; if (state.networkFailure) throw new Error("private network details"); return state.response; },
    resend: async (input) => { state.resend = input; return { error: state.resendError }; },
    signInWithOtp: async (input) => { state.loginOtp = input; return { error: state.loginOtpError }; },
    verifyOtp: async (input) => { state.otp = input; return { data: state.otpData, error: state.otpError }; },
    signOut: async (input) => { state.signOut = input; return { error: null }; }
  } };
}
export const studentProfiles = { userId: "user_id" };
export function getDb() {
  state.mirrorCalls = (state.mirrorCalls || 0) + 1;
  if (state.mirrorUnavailable) throw new Error("no optional mirror");
  return { insert: () => ({ values: (values) => ({ onConflictDoUpdate: async () => { state.mirror = values; } }) }) };
}
`;
const stubbed = new Set([
  "@/lib/supabase/config", "@/lib/supabase/server",
  "@/lib/auth", "@/db", "@/db/schema",
]);
const vite = await createServer({
  appType: "custom", configFile: false, root,
  plugins: [{
    name: "isolated-auth-dependencies", enforce: "pre",
    resolveId(id) { if (id === "@/lib/location-server" || id === "@/lib/location-data") return fileURLToPath(new URL("../lib/" + id.split("/").at(-1) + ".ts", import.meta.url)); if (stubbed.has(id) || id === "test:auth-state") return "\0test:auth-state"; },
    load(id) { if (id === "\0test:auth-state") return mockModule; },
  }],
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { state } = await vite.ssrLoadModule("test:auth-state");
const { registerAction, resendVerificationAction, verifyEmailAction, sendLoginCodeAction, verifyLoginCodeAction } = await vite.ssrLoadModule("/app/auth/actions.ts");
after(() => vite.close());
beforeEach(() => {
  for (const key of Object.keys(state)) delete state[key];
  state.response = { data: { user: { id: "synthetic-user", identities: [{ id: "synthetic-identity" }] }, session: null }, error: null };
  state.otpData = { session: { access_token: "verified-login-session" }, user: { email_confirmed_at: "2026-10-25T10:00:00Z" } };
});

function registration(overrides = {}) {
  const form = new FormData();
  for (const [key, value] of Object.entries({
    firstName: " Synthetic ", lastName: " Student ", email: " Student@Example.test ",
    mobile: "0710000000", country: "ZA", city: "Pretoria", province: "Gauteng", institution: "Synthetic School",
    academicLevel: "Grade 12", password: "Synthetic-Only-729!", confirmPassword: "Synthetic-Only-729!", terms: "on", ...overrides,
  })) form.set(key, value);
  return form;
}
async function redirectUrl(action, form) {
  await assert.rejects(action(form), (error) => {
    assert.equal(error.message, "NEXT_REDIRECT");
    assert.ok(error.digest);
    state.destination = new URL(error.digest.split(";")[2], "https://academy.example.test");
    return true;
  });
  return state.destination;
}

test("valid registration passes all profile fields and waits for email verification", async () => {
  const url = await redirectUrl(registerAction, registration());
  assert.equal(url.pathname, "/verify-email");
  assert.equal(url.searchParams.get("email"), "student@example.test");
  assert.deepEqual(state.signup.options.data, {
    first_name: "Synthetic", last_name: "Student", mobile: "0710000000", country: "ZA", city: "Pretoria", province: "Gauteng",
    institution: "Synthetic School", academic_level: "Grade 12", terms_accepted_at: state.signup.options.data.terms_accepted_at,
  });
  assert.ok(Number.isFinite(Date.parse(state.signup.options.data.terms_accepted_at)));
  assert.equal(state.signup.options.emailRedirectTo, "https://academy.example.test/auth/confirm?next=/dashboard");
  assert.equal(state.mirrorCalls, undefined);
});

test("invalid details never reach the auth provider", async () => {
  for (const override of [{ terms: "" }, { confirmPassword: "different" }, { email: "invalid" }, { mobile: "bad" }]) {
    const url = await redirectUrl(registerAction, registration(override));
    assert.equal(url.pathname, "/register");
    assert.ok(url.searchParams.get("error"));
    assert.equal(state.signup, undefined);
  }
});

test("duplicate errors and obfuscated responses keep the same neutral verification route", async () => {
  const normal = (await redirectUrl(registerAction, registration())).href;
  for (const code of ["user_already_exists", "email_exists"]) {
    state.response = { data: { user: null, session: null }, error: { code } };
    assert.equal((await redirectUrl(registerAction, registration())).href, normal);
  }
  state.response = { data: { user: { id: "obfuscated", identities: [] }, session: null }, error: null };
  assert.equal((await redirectUrl(registerAction, registration())).href, normal);
  assert.equal(state.mirrorCalls, undefined);
});

test("only a verified authenticated signup can reach the dashboard", async () => {
  state.response.data.session = { access_token: "synthetic-token" };
  assert.equal((await redirectUrl(registerAction, registration())).pathname, "/verify-email");
  state.response.data.user.email_confirmed_at = "2026-09-22T10:00:00Z";
  assert.equal((await redirectUrl(registerAction, registration())).pathname, "/dashboard");
  assert.equal(state.mirror.userId, "synthetic-user");
});

test("optional mirror failure does not fail verified signup", async () => {
  state.response.data.session = { access_token: "synthetic-token" };
  state.response.data.user.email_confirmed_at = "2026-09-22T10:00:00Z";
  state.mirrorUnavailable = true;
  assert.equal((await redirectUrl(registerAction, registration())).pathname, "/dashboard");
});

for (const [code, expected] of [
  ["over_email_send_rate_limit", /Wait a few minutes/],
  ["weak_password", /stronger password/],
  ["email_address_invalid", /Check your email/],
  ["email_address_not_authorized", /delivery is unavailable/],
  ["signup_disabled", /registrations are temporarily unavailable/],
  ["unexpected_failure", /contact us/i],
]) {
  test(`signup handles ${code} without disclosing raw errors`, async (t) => {
    const log = t.mock.method(console, "error", () => {});
    state.response.error = { code, status: 400, message: "private email and database details" };
    const url = await redirectUrl(registerAction, registration());
    assert.equal(url.pathname, "/register");
    assert.match(url.searchParams.get("error"), expected);
    assert.doesNotMatch(JSON.stringify(log.mock.calls.map(call => call.arguments)), /private|student@example|Synthetic-Only/);
    assert.equal(state.mirrorCalls, undefined);
  });
}

test("network and configuration failures offer retry and account recovery", async (t) => {
  t.mock.method(console, "error", () => {});
  for (const key of ["unavailable", "networkFailure"]) {
    state[key] = true;
    const url = await redirectUrl(registerAction, registration());
    assert.match(url.searchParams.get("error"), /temporarily unavailable/);
    delete state[key];
  }
});

test("missing user cannot be reported as successful registration", async (t) => {
  t.mock.method(console, "error", () => {});
  state.response.data.user = null;
  assert.equal((await redirectUrl(registerAction, registration())).pathname, "/register");
});

test("failed resend never reports an email was sent", async (t) => {
  t.mock.method(console, "error", () => {});
  state.resendError = { code: "unexpected_failure", status: 500 };
  const url = await redirectUrl(resendVerificationAction, registration());
  assert.ok(url.searchParams.get("error"));
  assert.equal(url.searchParams.has("resent"), false);
  state.resendError = null;
  assert.equal((await redirectUrl(resendVerificationAction, registration())).searchParams.get("resent"), "1");
});

test("resend connection failure keeps recovery on the verification page", async (t) => {
  t.mock.method(console, "error", () => {});
  state.unavailable = true;
  const url = await redirectUrl(resendVerificationAction, registration());
  assert.equal(url.pathname, "/verify-email");
  assert.match(url.searchParams.get("error"), /could not be requested/);
  assert.equal(url.searchParams.has("resent"), false);
});

test("six-digit verification rejects invalid or expired codes and accepts valid codes", async () => {
  const form = registration();
  form.set("token", "123");
  assert.equal((await redirectUrl(verifyEmailAction, form)).pathname, "/verify-email");
  assert.equal(state.otp, undefined);
  form.set("token", "123456");
  state.otpError = { code: "otp_expired" };
  assert.equal((await redirectUrl(verifyEmailAction, form)).pathname, "/verify-email");
  state.otpError = null;
  assert.equal((await redirectUrl(verifyEmailAction, form)).pathname, "/dashboard");
  assert.deepEqual(state.otp, { email: "student@example.test", token: "123456", type: "signup" });
});

test("email sign-in sends a code only for an existing student account", async () => {
  const form = registration();
  form.set("next", "/dashboard/courses");
  const url = await redirectUrl(sendLoginCodeAction, form);
  assert.equal(url.pathname, "/login/code");
  assert.equal(url.searchParams.get("email"), "student@example.test");
  assert.equal(url.searchParams.get("next"), "/dashboard/courses");
  assert.equal(state.loginOtp.email, "student@example.test");
  assert.equal(state.loginOtp.options.shouldCreateUser, false);
  assert.equal(state.loginOtp.options.emailRedirectTo, "https://academy.example.test/auth/confirm?next=%2Fdashboard%2Fcourses");
  assert.equal(state.signup, undefined);
});

test("login code request never reveals missing student accounts", async () => {
  state.loginOtpError = { code: "user_not_found", message: "User not found", status: 422 };
  const url = await redirectUrl(sendLoginCodeAction, registration());
  assert.equal(url.pathname, "/login/code");
  assert.equal(url.searchParams.get("sent"), "1");
  assert.equal(state.loginOtp.options.shouldCreateUser, false);
});

test("six-digit login OTP is validated and exchanged for a verified session", async () => {
  const form = registration();
  form.set("token", " 12 34 56 ");
  form.set("next", "/dashboard/courses");
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/dashboard/courses");
  assert.deepEqual(state.otp, { email: "student@example.test", token: "123456", type: "email" });

  form.set("token", "12345");
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/login/code");
  assert.equal(state.otp.token, "123456");
});

test("expired codes, missing sessions and unverified identities never sign in", async () => {
  const form = registration();
  form.set("token", "123456");
  state.otpError = { code: "otp_expired" };
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/login/code");
  state.otpError = null;
  state.otpData = { session: null, user: { email_confirmed_at: "2026-10-25T10:00:00Z" } };
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/login/code");
  state.otpData = { session: { access_token: "synthetic" }, user: { email_confirmed_at: null } };
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/login/code");
  assert.deepEqual(state.signOut, { scope: "local" });
});

test("email confirmation does not grant dashboard access without a verified session", async () => {
  const form = registration();
  form.set("token", "123456");
  state.otpData = { session: null, user: { email_confirmed_at: null } };
  assert.equal((await redirectUrl(verifyEmailAction, form)).pathname, "/verify-email");
});

test("login code redirects reject unsafe return paths", async () => {
  const form = registration();
  form.set("token", "123456");
  form.set("next", "https://attacker.example.test/steal");
  assert.equal((await redirectUrl(verifyLoginCodeAction, form)).pathname, "/dashboard");
});
