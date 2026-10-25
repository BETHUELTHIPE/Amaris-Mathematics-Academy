import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const mock = `
export const state = {};
export function getSiteUrl() { return "https://academy.example.test"; }
export class ApplicationError extends Error { constructor(status, message) { super(message); this.status = status; } }
export async function applicantToken() { state.tokenChecked = true; if (state.unauthorized) throw new ApplicationError(401, "Sign in first."); return "synthetic-private-token"; }
export async function applicationRequest(path, init, token) {
  state.forwarded = { path, method: init.method, data: init.body, token };
  return Response.json(state.backendBody || { application: { reference: "AMARIS-TUTOR-TEST" } }, { status: state.backendStatus || 201 });
}
export async function createSupabaseServerClient() { return { auth: {
  signUp: async input => { state.signup = input; return { error: state.authError }; },
  signInWithPassword: async input => { state.login = input; return { data: { user: { id: "synthetic" } }, error: state.authError }; },
  verifyOtp: async input => { state.otp = input; return { data: state.otpData ?? { session: { access_token: "test" }, user: { email_confirmed_at: "2026-10-25" } }, error: state.authError }; },
  getUser: async () => ({ data: { user: { email_confirmed_at: state.unverified ? null : "2026-10-25" } }, error: state.userError }),
  signOut: async options => { state.signOut = options; return { error: null }; },
  resend: async input => { state.resend = input; return { error: state.authError }; }
} }; }
`;
const stubs = new Set(["@/lib/supabase/config", "@/lib/supabase/server", "@/lib/tutor-applications", "test:applicants"]);
const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)), configFile: false, appType: "custom",
  plugins: [{ name: "applicant-test-services", enforce: "pre", resolveId(id) { if (id === "@/lib/location-server" || id === "@/lib/location-data") return fileURLToPath(new URL("../lib/" + id.split("/").at(-1) + ".ts", import.meta.url)); if (stubs.has(id)) return "\0test:applicants"; }, load(id) { if (id === "\0test:applicants") return mock; } }],
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { state } = await vite.ssrLoadModule("test:applicants");
const actions = await vite.ssrLoadModule("/app/tutor/register/actions.ts");
const { POST } = await vite.ssrLoadModule("/app/api/tutor-applications/route.ts");
after(() => vite.close());
beforeEach(() => { for (const key of Object.keys(state)) delete state[key]; });
function signup(overrides = {}) {
  const form = new FormData();
  for (const [key, value] of Object.entries({ firstName: "Synthetic", lastName: "Applicant", country: "ZA", province: "Gauteng", city: "Pretoria", email: "applicant@example.test", password: "Synthetic-Test-927!", confirmPassword: "Synthetic-Test-927!", consent: "on", ...overrides })) form.set(key, value);
  return form;
}
async function destination(action, data) {
  let url;
  await assert.rejects(action(data), error => {
    assert.equal(error.message, "NEXT_REDIRECT");
    url = new URL(error.digest.split(";")[2], "https://academy.example.test");
    return true;
  });
  return url;
}
test("applicants register, verify and sign in without claiming approved tutor membership", async () => {
  const registered = await destination(actions.registerApplicant, signup());
  assert.equal(registered.pathname, "/tutor/verify-email");
  assert.equal(state.signup.options.emailRedirectTo, "https://academy.example.test/auth/confirm?next=/tutor/apply");
  assert.equal(state.signup.options.data.role, undefined);
  assert.equal(state.signup.options.data.is_tutor, undefined);
  assert.equal((await destination(actions.verifyApplicant, new Map([["email", "applicant@example.test"], ["token", "123456"]]))).pathname, "/tutor/apply");
  assert.equal(state.otp.type, "signup");
  assert.equal((await destination(actions.loginApplicant, signup())).pathname, "/tutor/apply");
});
test("tutor applicant is blocked until email is confirmed even with correct password", async () => {
  state.unverified = true;
  const location = await destination(actions.loginApplicant, signup());
  assert.equal(location.pathname, "/tutor/verify-email");
  assert.deepEqual(state.signOut, { scope: "local" });
  state.signOut = undefined;
  const verify = await destination(actions.verifyApplicant, new Map([["email", "applicant@example.test"], ["token", "123456"]]));
  assert.equal(verify.pathname, "/tutor/verify-email");
  assert.deepEqual(state.signOut, { scope: "local" });
});

test("tutor OTP confirmation must return a session and a confirmed account", async () => {
  state.otpData = { session: null, user: { email_confirmed_at: "2026-10-25" } };
  assert.equal((await destination(actions.verifyApplicant, new Map([["email", "applicant@example.test"], ["token", "123456"]]))).pathname, "/tutor/verify-email");
  state.otpData = { session: { access_token: "test" }, user: { email_confirmed_at: null } };
  assert.equal((await destination(actions.verifyApplicant, new Map([["email", "applicant@example.test"], ["token", "123456"]]))).pathname, "/tutor/verify-email");
  assert.deepEqual(state.signOut, { scope: "local" });
});

test("invalid registration and failed login never advance to the application", async () => {
  for (const override of [{ consent: "" }, { confirmPassword: "wrong" }, { password: "weak" }, { email: "bad" }]) {
    assert.equal((await destination(actions.registerApplicant, signup(override))).pathname, "/tutor/register");
    assert.equal(state.signup, undefined);
  }
  state.authError = { code: "invalid_credentials" };
  assert.equal((await destination(actions.loginApplicant, signup())).pathname, "/tutor/apply/login");
});
test("duplicate signup responses do not disclose whether an applicant already exists", async () => {
  const normal = (await destination(actions.registerApplicant, signup())).href;
  state.authError = { code: "email_exists" };
  assert.equal((await destination(actions.registerApplicant, signup())).href, normal);
});
test("cross-origin application submissions are rejected before checking credentials", async () => {
  const request = new Request("https://academy.example.test/api/tutor-applications", { method: "POST", headers: { Origin: "https://attacker.example.test", Accept: "application/json" }, body: new FormData() });
  const response = await POST(request);
  assert.equal(response.status, 403);
  assert.equal(state.tokenChecked, undefined);
  assert.equal(state.forwarded, undefined);
});
test("qualification multipart form preserves file bytes and returns private receipt", async () => {
  const form = new FormData();
  form.set("full_name", "Synthetic Applicant");
  form.set("country", "ZA"); form.set("province", "Gauteng"); form.set("city", "Pretoria");
  form.append("documents", new File(["%PDF-test"], "qualification.pdf", { type: "application/pdf" }));
  const response = await POST(new Request("https://academy.example.test/api/tutor-applications", { method: "POST", body: form, headers: { Origin: "https://academy.example.test", Accept: "application/json" } }));
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.equal(state.forwarded.token, "synthetic-private-token");
  assert.equal(await state.forwarded.data.get("documents").text(), "%PDF-test");
  assert.equal((await response.json()).application.reference, "AMARIS-TUTOR-TEST");
});
test("expired applicant session does not forward qualifications", async () => {
  state.unauthorized = true;
  const response = await POST(new Request("https://academy.example.test/api/tutor-applications", { method: "POST", body: new FormData(), headers: { Origin: "https://academy.example.test", Accept: "application/json" } }));
  assert.equal(response.status, 401);
  assert.equal(state.forwarded, undefined);
});
test("oversized uploads are rejected even without a content-length header", async () => {
  const response = await POST(new Request("https://academy.example.test/api/tutor-applications", { method: "POST", body: new Uint8Array(16 * 1024 * 1024 + 1), headers: { Origin: "https://academy.example.test", Accept: "application/json", "Content-Type": "multipart/form-data; boundary=test" } }));
  assert.equal(response.status, 413);
  assert.equal(state.forwarded, undefined);
});
test("ordinary HTML form submits redirect to the saved application without JavaScript", async () => {
  const form = new FormData();
  for (const [key, value] of Object.entries({ country: "ZA", province: "Gauteng", city: "Pretoria" })) form.set(key, value);
  const response = await POST(new Request("https://academy.example.test/api/tutor-applications", { method: "POST", body: form, headers: { Origin: "https://academy.example.test", Accept: "text/html" } }));
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "https://academy.example.test/tutor/apply");
});

test("missing application location returns named errors before forwarding files", async () => {
  const response = await POST(new Request("https://academy.example.test/api/tutor-applications", { method: "POST", body: new FormData(), headers: { Origin: "https://academy.example.test", Accept: "application/json" } }));
  assert.equal(response.status, 400);
  assert.deepEqual(Object.keys(await response.json()).sort(), ["city", "country", "province"]);
  assert.equal(state.forwarded, undefined);
});
