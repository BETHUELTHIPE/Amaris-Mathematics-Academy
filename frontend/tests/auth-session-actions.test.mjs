import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const mockModule = `
export const state = {};
export function getSiteUrl() { return "https://academy.example.test"; }
export function safeRelativePath(path) {
  if (!path || !path.startsWith("/") || path.startsWith("//")) return "/dashboard";
  return path;
}
export async function createSupabaseServerClient() {
  return { auth: {
    signUp: async () => state.signupResponse ?? { data: { user: null, session: null }, error: null },
    resend: async () => ({ error: null }),
    verifyOtp: async () => ({ error: null }),
    signInWithPassword: async (input) => { state.loginInput = input; return { error: state.loginError ?? null }; },
    signInWithOAuth: async (input) => {
      state.oauthInput = input;
      return state.oauthResponse ?? { data: { url: "https://accounts.google.test/oauth/start" }, error: null };
    },
    resetPasswordForEmail: async (email, options) => {
      state.recoveryInput = { email, options };
      return { error: state.recoveryError ?? null };
    },
    getUser: async () => ({ data: { user: state.user ?? null }, error: state.getUserError ?? null }),
    updateUser: async (input) => { state.updateInput = input; return { error: state.updateError ?? null }; },
    signOut: async (input) => { state.signOutInput = input; return { error: state.signOutError ?? null }; },
  } };
}
export const studentProfiles = { userId: "user_id" };
export function getDb() {
  return { insert: () => ({ values: () => ({ onConflictDoUpdate: async () => {} }) }) };
}
`;

const stubbed = new Set([
  "@/lib/supabase/config", "@/lib/supabase/server",
  "@/lib/auth", "@/db", "@/db/schema",
]);
const vite = await createServer({
  appType: "custom",
  configFile: false,
  root,
  plugins: [{
    name: "isolated-session-auth-dependencies",
    enforce: "pre",
    resolveId(id) {
      if (stubbed.has(id) || id === "test:session-auth-state") return "\0test:session-auth-state";
    },
    load(id) {
      if (id === "\0test:session-auth-state") return mockModule;
    },
  }],
  server: { middlewareMode: true, hmr: false, ws: false },
});

const { state } = await vite.ssrLoadModule("test:session-auth-state");
const {
  loginAction,
  googleAuthAction,
  linkedInAuthAction,
  forgotPasswordAction,
  resetPasswordAction,
  signOutAction,
} = await vite.ssrLoadModule("/app/auth/actions.ts");

after(() => vite.close());
beforeEach(() => {
  for (const key of Object.keys(state)) delete state[key];
});

function form(values) {
  const result = new FormData();
  for (const [key, value] of Object.entries(values)) result.set(key, value);
  return result;
}

async function redirectUrl(action, data = new FormData()) {
  await assert.rejects(action(data), (error) => {
    assert.equal(error.message, "NEXT_REDIRECT");
    assert.ok(error.digest);
    state.destination = new URL(error.digest.split(";")[2], "https://academy.example.test");
    return true;
  });
  return state.destination;
}

test("successful password login redirects only to a safe student path", async () => {
  const url = await redirectUrl(loginAction, form({
    email: " Student@Example.test ",
    password: "Synthetic-Only-729!",
    next: "/dashboard?from=login",
  }));
  assert.equal(url.pathname, "/dashboard");
  assert.equal(url.searchParams.get("from"), "login");
  assert.deepEqual(state.loginInput, {
    email: "student@example.test",
    password: "Synthetic-Only-729!",
  });

  const unsafe = await redirectUrl(loginAction, form({
    email: "student@example.test",
    password: "Synthetic-Only-729!",
    next: "//evil.example",
  }));
  assert.equal(unsafe.pathname, "/dashboard");
});

test("unverified login returns the student to email verification without leaking provider detail", async () => {
  state.loginError = { message: "Email not confirmed: internal provider detail", code: "email_not_confirmed" };
  const url = await redirectUrl(loginAction, form({
    email: "student@example.test",
    password: "Synthetic-Only-729!",
  }));
  assert.equal(url.pathname, "/verify-email");
  assert.equal(url.searchParams.get("email"), "student@example.test");
  assert.equal(url.searchParams.get("error"), "Verify your email before logging in.");
});

test("invalid credentials use one generic response and rate limits use the branded 429 page", async () => {
  state.loginError = { message: "Invalid login credentials for private account", code: "invalid_credentials" };
  let url = await redirectUrl(loginAction, form({
    email: "student@example.test",
    password: "wrong",
  }));
  assert.equal(url.pathname, "/login");
  assert.equal(url.searchParams.get("error"), "The email or password is incorrect. Please try again.");
  assert.doesNotMatch(url.href, /private account/);

  state.loginError = { message: "Too many requests", code: "over_request_rate_limit" };
  url = await redirectUrl(loginAction, form({
    email: "student@example.test",
    password: "wrong",
  }));
  assert.equal(url.pathname, "/errors/429");
});

test("Google authentication uses PKCE callback and preserves only a safe next path", async () => {
  const url = await redirectUrl(googleAuthAction, form({
    next: "/courses/algebra?from=google",
  }));
  assert.equal(url.origin, "https://accounts.google.test");
  assert.deepEqual(state.oauthInput, {
    provider: "google",
    options: {
      redirectTo: "https://academy.example.test/auth/callback?next=%2Fcourses%2Falgebra%3Ffrom%3Dgoogle",
    },
  });

  await redirectUrl(googleAuthAction, form({ next: "//evil.example/steal" }));
  assert.equal(
    state.oauthInput.options.redirectTo,
    "https://academy.example.test/auth/callback?next=%2Fdashboard",
  );
});

test("Google provider errors return a generic student-safe message", async () => {
  state.oauthResponse = {
    data: { url: null },
    error: { message: "private provider configuration detail", code: "provider_disabled", status: 400 },
  };
  const url = await redirectUrl(googleAuthAction, form({ next: "/dashboard" }));
  assert.equal(url.pathname, "/login");
  assert.equal(
    url.searchParams.get("error"),
    "Google sign-in is temporarily unavailable. Please use your email and password or try again shortly.",
  );
  assert.doesNotMatch(url.href, /provider_disabled|configuration detail/);
});

test("LinkedIn OIDC authentication uses the shared PKCE callback and safe next path", async () => {
  state.oauthResponse = { data: { url: "https://www.linkedin.test/oauth/start" }, error: null };
  const url = await redirectUrl(linkedInAuthAction, form({
    next: "/dashboard?from=linkedin",
  }));
  assert.equal(url.origin, "https://www.linkedin.test");
  assert.deepEqual(state.oauthInput, {
    provider: "linkedin_oidc",
    options: {
      redirectTo: "https://academy.example.test/auth/callback?next=%2Fdashboard%3Ffrom%3Dlinkedin",
    },
  });

  await redirectUrl(linkedInAuthAction, form({ next: "//evil.example/steal" }));
  assert.equal(
    state.oauthInput.options.redirectTo,
    "https://academy.example.test/auth/callback?next=%2Fdashboard",
  );
});

test("LinkedIn provider errors return a generic student-safe message", async () => {
  state.oauthResponse = {
    data: { url: null },
    error: { message: "private LinkedIn provider detail", code: "provider_disabled", status: 400 },
  };
  const url = await redirectUrl(linkedInAuthAction, form({ next: "/dashboard" }));
  assert.equal(url.pathname, "/login");
  assert.equal(
    url.searchParams.get("error"),
    "LinkedIn sign-in is temporarily unavailable. Please use Google, email and password, or try again shortly.",
  );
  assert.doesNotMatch(url.href, /provider_disabled|provider detail/);
});

test("password recovery is neutral and uses the production confirmation route", async () => {
  const url = await redirectUrl(forgotPasswordAction, form({ email: " Student@Example.test " }));
  assert.equal(url.pathname, "/forgot-password");
  assert.equal(url.searchParams.get("sent"), "1");
  assert.deepEqual(state.recoveryInput, {
    email: "student@example.test",
    options: {
      redirectTo: "https://academy.example.test/auth/confirm?next=/reset-password",
    },
  });
});

test("invalid recovery email never reaches Supabase and provider failures remain generic", async () => {
  let url = await redirectUrl(forgotPasswordAction, form({ email: "not-an-email" }));
  assert.equal(url.pathname, "/forgot-password");
  assert.ok(url.searchParams.get("error"));
  assert.equal(state.recoveryInput, undefined);

  state.recoveryError = { message: "private SMTP/provider detail", code: "unexpected" };
  url = await redirectUrl(forgotPasswordAction, form({ email: "student@example.test" }));
  assert.equal(url.pathname, "/forgot-password");
  assert.equal(url.searchParams.get("error"), "We could not request a reset email right now. Please try again.");
  assert.doesNotMatch(url.href, /SMTP|provider detail/);
});

test("password reset requires a recovery session and enforces the local strength policy", async () => {
  let url = await redirectUrl(resetPasswordAction, form({
    password: "short",
    confirmPassword: "short",
  }));
  assert.equal(url.pathname, "/reset-password");
  assert.equal(state.updateInput, undefined);

  state.user = null;
  url = await redirectUrl(resetPasswordAction, form({
    password: "Synthetic-Only-729!",
    confirmPassword: "Synthetic-Only-729!",
  }));
  assert.equal(url.pathname, "/forgot-password");
  assert.equal(state.updateInput, undefined);
});

test("successful password reset updates the user then revokes all sessions", async () => {
  state.user = { id: "synthetic-user" };
  const url = await redirectUrl(resetPasswordAction, form({
    password: "Synthetic-Only-729!",
    confirmPassword: "Synthetic-Only-729!",
  }));
  assert.equal(url.pathname, "/login");
  assert.equal(url.searchParams.get("password_updated"), "1");
  assert.deepEqual(state.updateInput, { password: "Synthetic-Only-729!" });
  assert.deepEqual(state.signOutInput, { scope: "global" });
});

test("ordinary sign-out revokes the current browser session", async () => {
  const url = await redirectUrl(signOutAction);
  assert.equal(url.pathname, "/login");
  assert.equal(url.searchParams.get("signed_out"), "1");
  assert.deepEqual(state.signOutInput, { scope: "local" });
});
