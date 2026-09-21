import assert from 'node:assert/strict';
import test, { after, beforeEach } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { NextRequest } from 'next/server.js';

// Execute the real actions, identity guard, callback, proxy and worker. Only the
// external Auth service and framework request context are replaced; no email or
// production account is used by this deterministic regression suite.
const root = fileURLToPath(new URL('..', import.meta.url));
const replacements = {
  '@/lib/supabase/server': `import { state } from 'test:auth-state'; export async function createSupabaseServerClient() { return { auth: state.auth }; }`,
  '@supabase/ssr': `import { state } from 'test:auth-state'; export function createServerClient(url, key, options) { state.options = options; return { auth: state.auth }; }`,
  '@/db': `import { state } from 'test:auth-state'; export function getDb() { return { insert() { return { values(value) { state.profile = value; return { async onConflictDoUpdate() { if (state.profileError) throw new Error('mirror unavailable'); } }; } }; } }; }`,
  '@/db/schema': `export const studentProfiles = { userId: 'userId' };`,
  'vinext/server/app-router-entry': `import { state } from 'test:auth-state'; export default { async fetch() { return state.response ?? new Response('ok'); } };`,
  'vinext/server/image-optimization': `export const DEFAULT_DEVICE_SIZES = []; export const DEFAULT_IMAGE_SIZES = []; export async function handleImageOptimization() { return new Response('image'); }`,
  'test:auth-state': `export const state = {};`,
};
const vite = await createServer({
  appType: 'custom', configFile: false, root,
  ssr: { noExternal: ['vinext', '@supabase/ssr'] },
  define: { __E2E_SYNTHETIC_STUDENT__: 'false' },
  plugins: [{ name: 'auth-test-boundaries', enforce: 'pre',
    resolveId(id) { if (id in replacements) return '\0' + id; },
    load(id) { return replacements[id.slice(1)]; },
  }],
  resolve: { alias: [{ find: /^@\/(?!db(?:\/|$)|lib\/supabase\/server$)(.*)/, replacement: root + '/$1' }] },
  server: { middlewareMode: true, hmr: false },
});
after(() => vite.close());
const { state } = await vite.ssrLoadModule('test:auth-state');
const auth = await vite.ssrLoadModule('/lib/auth.ts');
const actions = await vite.ssrLoadModule('/app/auth/actions.ts');
const callback = await vite.ssrLoadModule('/app/auth/confirm/route.ts');
const proxy = await vite.ssrLoadModule('/lib/supabase/proxy.ts');
const worker = (await vite.ssrLoadModule('/worker/index.ts')).default;
const verifiedUser = () => ({ id: '00000000-0000-4000-8000-000000000123', email: 'student@example.test', email_confirmed_at: '2026-09-21T00:00:00Z', user_metadata: { first_name: 'Test', last_name: 'Student' } });
const form = (values) => { const result = new FormData(); for (const [key, value] of Object.entries(values)) result.set(key, value); return result; };
const registration = () => ({ firstName: 'Test', lastName: 'Student', email: 'Student@Example.Test', mobile: '0712345678', province: 'Gauteng', institution: 'Synthetic School', academicLevel: 'Grade 12', password: 'Synthetic-Password-123', confirmPassword: 'Synthetic-Password-123', terms: 'on' });
async function destination(action, values = {}) {
  try { await action(form(values)); assert.fail('Expected redirect'); } catch (error) { if (!error.digest?.startsWith('NEXT_REDIRECT;')) throw error; return new URL(error.digest.split(';').slice(2, -2).join(';'), 'https://academy.example.test'); }
}
beforeEach(() => {
  process.env.SUPABASE_URL = 'https://auth.example.test';
  process.env.SUPABASE_PUBLISHABLE_KEY = 'test-publishable';
  process.env.SITE_URL = 'https://academy.example.test';
  state.calls = []; state.profile = undefined; state.profileError = false; state.response = undefined;
  state.results = { getUser: { data: { user: verifiedUser() }, error: null }, getClaims: { data: { claims: {} }, error: null }, signUp: { data: { user: verifiedUser(), session: null }, error: null } };
  state.auth = Object.fromEntries(['getUser', 'getClaims', 'signUp', 'verifyOtp', 'resend', 'signInWithPassword', 'resetPasswordForEmail', 'updateUser', 'signOut', 'exchangeCodeForSession'].map(name => [name, async (...args) => { state.calls.push({ name, args }); return state.results[name] ?? { data: {}, error: null }; }]));
});

test('confirmed Auth user is verified without any email_verified JWT claim', async () => {
  assert.equal((await auth.getStudentIdentity()).emailVerified, true);
  assert.equal(state.calls[0].name, 'getUser');
});
test('editable metadata cannot forge email verification', async () => {
  state.results.getUser.data.user.email_confirmed_at = null;
  state.results.getUser.data.user.user_metadata.email_verified = true;
  assert.equal((await auth.getStudentIdentity()).emailVerified, false);
  assert.equal((await destination(auth.requireVerifiedStudent)).pathname, '/verify-email');
});
test('anonymous users cannot gain verified student access', async () => {
  state.results.getUser.data.user.is_anonymous = true;
  assert.equal((await auth.getStudentIdentity()).emailVerified, false);
});
test('expired, rejected and absent sessions fail closed', async () => {
  for (const result of [{ data: { user: null }, error: null }, { data: { user: verifiedUser() }, error: new Error('revoked') }]) {
    state.results.getUser = result;
    assert.equal(await auth.getStudentIdentity(), null);
    const url = await destination(() => auth.requireVerifiedStudent('/learn/math/lesson'));
    assert.equal(url.pathname, '/login'); assert.equal(url.searchParams.get('next'), '/learn/math/lesson');
  }
});
for (const value of ['https://evil.example', '//evil.example', '/\\evil.example', '/auth/confirm?code=bad', '/login', '/reset-password']) {
  test(`login rejects unsafe or looping return path ${value}`, () => assert.equal(auth.safeRelativePath(value), '/dashboard'));
}
test('safe student return path survives login', () => assert.equal(auth.safeRelativePath('/learn/math/lesson?resume=1#board'), '/learn/math/lesson?resume=1#board'));
test('registration normalizes email, requires terms and requests a verification callback', async () => {
  const url = await destination(actions.registerAction, registration());
  assert.equal(url.pathname, '/verify-email'); assert.equal(url.searchParams.get('email'), 'student@example.test');
  const request = state.calls.find(call => call.name === 'signUp').args[0];
  assert.equal(request.options.emailRedirectTo, 'https://academy.example.test/auth/confirm?next=/dashboard');
  assert.equal(request.email, 'student@example.test'); assert.ok(request.options.data.terms_accepted_at);
});
for (const change of [{ password: 'weak', confirmPassword: 'weak' }, { confirmPassword: 'not matching' }, { terms: '' }, { email: 'invalid' }]) {
  test(`invalid registration never reaches Auth: ${Object.keys(change).join(',')}`, async () => {
    assert.equal((await destination(actions.registerAction, { ...registration(), ...change })).pathname, '/register');
    assert.equal(state.calls.length, 0);
  });
}
test('profile mirror outage does not invalidate a successful registration', async () => {
  state.profileError = true;
  assert.equal((await destination(actions.registerAction, registration())).pathname, '/verify-email');
});
test('signup provider failure never claims the profile was created', async () => {
  state.results.signUp = { data: {}, error: new Error('provider unavailable') };
  const url = await destination(actions.registerAction, registration());
  assert.equal(url.pathname, '/register'); assert.ok(url.searchParams.has('error')); assert.equal(state.profile, undefined);
});
test('six digit code verifies with the signup flow', async () => {
  assert.equal((await destination(actions.verifyEmailAction, { email: ' Student@Example.Test ', token: '123 456' })).pathname, '/dashboard');
  assert.deepEqual(state.calls[0].args[0], { email: 'student@example.test', token: '123456', type: 'signup' });
});
test('malformed code is rejected without an Auth request', async () => {
  assert.equal((await destination(actions.verifyEmailAction, { email: 'student@example.test', token: '123' })).pathname, '/verify-email');
  assert.equal(state.calls.length, 0);
});
test('expired or reused code shows an error', async () => {
  state.results.verifyOtp = { error: new Error('expired') };
  const url = await destination(actions.verifyEmailAction, { email: 'student@example.test', token: '123456' });
  assert.equal(url.pathname, '/verify-email'); assert.ok(url.searchParams.has('error'));
});
test('login works without an optional next field', async () => {
  assert.equal((await destination(actions.loginAction, { email: ' Student@Example.Test ', password: 'valid' })).pathname, '/dashboard');
  assert.equal(state.calls[0].name, 'signInWithPassword');
});
test('incorrect password uses generic feedback', async () => {
  state.results.signInWithPassword = { error: new Error('invalid_credentials') };
  const url = await destination(actions.loginAction, { email: 'student@example.test', password: 'wrong' });
  assert.equal(url.pathname, '/login'); assert.match(url.searchParams.get('error'), /email or password is incorrect/);
});
test('unconfirmed login directs the student to verification', async () => {
  state.results.signInWithPassword = { error: new Error('Email not confirmed') };
  assert.equal((await destination(actions.loginAction, { email: 'student@example.test', password: 'valid' })).pathname, '/verify-email');
});
for (const [method, action, pathname, flag] of [['resend', actions.resendVerificationAction, '/verify-email', 'resent'], ['resetPasswordForEmail', actions.forgotPasswordAction, '/forgot-password', 'sent']]) {
  test(`${method} reports provider failure without claiming delivery`, async () => {
    state.results[method] = { error: new Error('SMTP unavailable') };
    const url = await destination(action, { email: 'student@example.test' });
    assert.equal(url.pathname, pathname); assert.ok(url.searchParams.has('error')); assert.equal(url.searchParams.has(flag), false);
  });
  test(`${method} enforces provider rate limits`, async () => {
    state.results[method] = { error: new Error('email rate limit exceeded') };
    assert.equal((await destination(action, { email: 'student@example.test' })).pathname, '/errors/429');
  });
  test(`${method} accepts delivery request without exposing account existence`, async () => {
    assert.equal((await destination(action, { email: 'student@example.test' })).searchParams.get(flag), '1');
  });
}
for (const query of ['code=pkce-code&next=/reset-password', 'token_hash=hash&type=recovery', 'token_hash=hash&type=recovery&next=https://evil.example']) {
  test(`recovery callback reaches the new-password form: ${query}`, async () => {
    const response = await callback.GET(new NextRequest('https://academy.example.test/auth/confirm?' + query));
    assert.equal(new URL(response.headers.get('location')).pathname, '/reset-password');
    assert.match(response.headers.get('cache-control'), /no-store/);
  });
}
test('signup callback rejects external redirect after verification', async () => {
  const response = await callback.GET(new NextRequest('https://academy.example.test/auth/confirm?token_hash=hash&type=signup&next=//evil.example'));
  assert.equal(response.headers.get('location'), 'https://academy.example.test/dashboard');
});
test('expired recovery link offers another reset', async () => {
  state.results.exchangeCodeForSession = { error: new Error('expired') };
  const response = await callback.GET(new NextRequest('https://academy.example.test/auth/confirm?code=used&next=/reset-password'));
  assert.equal(new URL(response.headers.get('location')).pathname, '/forgot-password');
});
test('missing and unsupported callback tokens fail closed', async () => {
  for (const query of ['', '?token_hash=hash&type=unsupported']) {
    const response = await callback.GET(new NextRequest('https://academy.example.test/auth/confirm' + query));
    assert.equal(new URL(response.headers.get('location')).pathname, '/login');
  }
  assert.equal(state.calls.length, 0);
});
test('password reset requires a validated current user', async () => {
  state.results.getUser = { data: { user: null }, error: null };
  assert.equal((await destination(actions.resetPasswordAction, registration())).pathname, '/forgot-password');
  assert.equal(state.calls.some(call => call.name === 'updateUser'), false);
});
test('password reset validates confirmation before updating and revokes all refresh sessions', async () => {
  assert.equal((await destination(actions.resetPasswordAction, registration())).searchParams.get('password_updated'), '1');
  assert.deepEqual(state.calls.map(call => call.name), ['getUser', 'updateUser', 'signOut']);
  assert.deepEqual(state.calls[2].args[0], { scope: 'global' });
});
test('password update failure leaves success unset', async () => {
  state.results.updateUser = { error: new Error('same password') };
  const url = await destination(actions.resetPasswordAction, registration());
  assert.equal(url.pathname, '/reset-password'); assert.ok(url.searchParams.has('error'));
  assert.equal(state.calls.some(call => call.name === 'signOut'), false);
});
test('logout revokes the current session', async () => {
  assert.equal((await destination(actions.signOutAction)).searchParams.get('signed_out'), '1');
  assert.deepEqual(state.calls[0].args[0], { scope: 'local' });
});
test('logout failure never reports secure signout', async () => {
  state.results.signOut = { error: new Error('service unavailable') };
  await assert.rejects(actions.signOutAction, /could not sign you out/);
});
test('refresh forwards rotated cookies to the server render and browser', async () => {
  state.auth.getClaims = async () => { state.options.cookies.setAll([{ name: 'sb-test-auth-token', value: 'fresh', options: { path: '/', httpOnly: true } }], { 'Cache-Control': 'private, no-store' }); return { error: null }; };
  const response = await proxy.refreshSupabaseSession(new NextRequest('https://academy.example.test/learn/math/one', { headers: { cookie: 'sb-test-auth-token=stale' } }));
  assert.match(response.headers.get('x-middleware-request-cookie'), /sb-test-auth-token=fresh/);
  assert.equal(response.cookies.get('sb-test-auth-token').value, 'fresh');
  assert.match(response.headers.get('cache-control'), /no-store/);
});
test('expired lesson session redirects without losing cookie cleanup', async () => {
  state.auth.getClaims = async () => { state.options.cookies.setAll([{ name: 'sb-test-auth-token', value: '', options: { path: '/', maxAge: 0 } }], {}); return { error: new Error('expired') }; };
  const response = await proxy.refreshSupabaseSession(new NextRequest('https://academy.example.test/learn/math/one', { headers: { cookie: 'sb-test-auth-token=expired' } }));
  assert.equal(new URL(response.headers.get('location')).pathname, '/session-expired');
  assert.equal(response.cookies.get('sb-test-auth-token').value, '');
  assert.match(response.headers.get('cache-control'), /no-store/);
});
for (const path of ['/login', '/register', '/verify-email', '/auth/confirm', '/reset-password', '/forgot-password', '/learn/math/one', '/dashboard']) {
  test(`${path} response is never publicly cached`, async () => {
    const response = await worker.fetch(new Request('https://academy.example.test' + path), {}, {});
    assert.match(response.headers.get('cache-control'), /private, no-store/);
  });
}
test('personalized public headers and refreshed sessions are not cacheable', async () => {
  for (const [cookie, response] of [['sb-test-auth-token.0=session', new Response('personalized')], ['', new Response('new session', { headers: { 'Set-Cookie': 'sb-test-auth-token=new' } })]]) {
    state.response = response;
    const result = await worker.fetch(new Request('https://academy.example.test/', { headers: { cookie } }), {}, {});
    assert.match(result.headers.get('cache-control'), /private, no-store/);
  }
});
test('verification attempts use the authentication rate limiter', async () => {
  const keys = [];
  const response = await worker.fetch(new Request('https://academy.example.test/verify-email', { method: 'POST', headers: { 'cf-connecting-ip': '192.0.2.1' } }), { AUTH_RATE_LIMITER: { async limit({ key }) { keys.push(key); return { success: false }; } } }, {});
  assert.equal(response.status, 429); assert.deepEqual(keys, ['auth:192.0.2.1']);
});
