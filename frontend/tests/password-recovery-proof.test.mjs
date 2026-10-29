import assert from "node:assert/strict";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  configFile: false,
  appType: "custom",
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { issuePasswordRecoveryProof, isValidPasswordRecoveryProof, getVerifiedRecoveryIdentity } =
  await vite.ssrLoadModule("/lib/password-recovery-proof.ts");
after(() => vite.close());

const secret = "test-only-recovery-proof-secret-" + "x".repeat(48);
const a = { userId: "11111111-1111-4111-8111-111111111111", sessionId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" };
const b = { userId: a.userId, sessionId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" };
const c = { userId: "22222222-2222-4222-8222-222222222222", sessionId: a.sessionId };
const now = Date.parse("2026-10-26T10:00:00Z");

test("recovery proof is cryptographically signed and short lived", async () => {
  const proof = await issuePasswordRecoveryProof(a, secret, now);
  assert.ok(proof);
  assert.notEqual(proof, "1");
  assert.match(proof, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
  assert.equal(await isValidPasswordRecoveryProof(proof, a, secret, now + 899000), true);
  assert.equal(await isValidPasswordRecoveryProof(proof, a, secret, now + 900000), false);
  assert.equal(await isValidPasswordRecoveryProof(proof, a, secret, now - 1), false);
});

test("forged, wrong-session, wrong-user and missing-secret recovery cookies fail closed", async () => {
  const proof = await issuePasswordRecoveryProof(a, secret, now);
  assert.equal(await isValidPasswordRecoveryProof("1", a, secret, now), false);
  assert.equal(await isValidPasswordRecoveryProof(proof + "a", a, secret, now), false);
  assert.equal(await isValidPasswordRecoveryProof(proof, b, secret, now), false);
  assert.equal(await isValidPasswordRecoveryProof(proof, c, secret, now), false);
  assert.equal(await isValidPasswordRecoveryProof(proof, a, undefined, now), false);
  assert.equal(await issuePasswordRecoveryProof(a, "short", now), null);
});

test("only authoritative, confirmed Supabase identity matching JWT subject and session is accepted", async () => {
  const subject = "12345678-1234-4234-8234-123456789abc";
  const session = "87654321-4321-4321-8321-cba987654321";
  const auth = ({ userId = subject, claimsId = subject, sessionId = session, confirmed = true, failed = false } = {}) => ({
    getUser: async () => ({ data: { user: { id: userId, email_confirmed_at: confirmed ? "2026-10-25" : null } }, error: failed ? { message: "offline" } : null }),
    getClaims: async () => ({ data: { claims: { sub: claimsId, session_id: sessionId } }, error: null }),
  });
  assert.deepEqual(await getVerifiedRecoveryIdentity(auth()), { userId: subject, sessionId: session });
  assert.equal(await getVerifiedRecoveryIdentity(auth({ confirmed: false })), null);
  assert.equal(await getVerifiedRecoveryIdentity(auth({ claimsId: "other" })), null);
  assert.equal(await getVerifiedRecoveryIdentity(auth({ sessionId: "" })), null);
  assert.equal(await getVerifiedRecoveryIdentity(auth({ failed: true })), null);
});
