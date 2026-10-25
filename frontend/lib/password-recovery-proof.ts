/**
 * Authenticated, short-lived password-reset proof.
 *
 * Unlike a literal "1" cookie, this HMAC is created only after Supabase
 * accepts a password-recovery OTP and rechecks the confirmed user. The
 * signature is bound to the Supabase user and verified session ID.
 *
 * Requires a separate, high-entropy PASSWORD_RECOVERY_SIGNING_SECRET on
 * the server; missing/weak secrets fail closed. Never send this proof to
 * client-side JavaScript, logs or analytics.
 */
import { PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS } from "@/lib/password-recovery";

export type RecoveryIdentity = { userId: string; sessionId: string };

type RecoveryClaims = { sub?: string; session_id?: string };
type RecoveryAuth = {
  getUser(): Promise<{
    data: { user: { id: string; email_confirmed_at?: string | null } | null };
    error: unknown;
  }>;
  getClaims(): Promise<{
    data: { claims: RecoveryClaims | null };
    error: unknown;
  }>;
};

export async function getVerifiedRecoveryIdentity(auth: RecoveryAuth): Promise<RecoveryIdentity | null> {
  try {
    const [user, claims] = await Promise.all([auth.getUser(), auth.getClaims()]);
    const confirmed = Boolean(user.data.user?.email_confirmed_at);
    const id = user.data.user?.id;
    const subject = claims.data.claims?.sub;
    const session = claims.data.claims?.session_id;
    if (user.error || claims.error || !confirmed ||
        !id || subject !== id || !session || !/^[0-9a-f-]{36}$/i.test(session)) {
      return null;
    }
    return { userId: id, sessionId: session };
  } catch {
    return null;
  }
}

function configuredSecret(value: string | undefined): string | null {
  // Require a high-entropy random secret, configured separately per environment.
  return value && value.length >= 43 ? value : null;
}

const encoder = new TextEncoder();
function toBase64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function fromBase64url(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]+$/.test(value) || value.length > 1024) {
    throw new Error("Invalid recovery proof");
  }
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), char => char.charCodeAt(0));
}
async function keyFor(secret: string) {
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

/** A verified recovery session creates a 15-minute, HttpOnly cookie payload. */
export async function issuePasswordRecoveryProof(
  identity: RecoveryIdentity,
  secretValue: string | undefined = process.env.PASSWORD_RECOVERY_SIGNING_SECRET,
  now = Date.now(),
): Promise<string | null> {
  const secret = configuredSecret(secretValue);
  if (!secret || !identity.userId || !identity.sessionId) return null;
  const payload = toBase64url(encoder.encode(JSON.stringify({
    v: 1, u: identity.userId, s: identity.sessionId, iat: now,
  })));
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", await keyFor(secret), encoder.encode(payload)));
  return `${payload}.${toBase64url(signature)}`;
}

/** Never grant a reset without a valid signature, expiry and current session. */
export async function isValidPasswordRecoveryProof(
  cookieValue: string | undefined,
  identity: RecoveryIdentity | null,
  secretValue: string | undefined = process.env.PASSWORD_RECOVERY_SIGNING_SECRET,
  now = Date.now(),
): Promise<boolean> {
  const secret = configuredSecret(secretValue);
  if (!cookieValue || !identity || !secret || cookieValue.length > 1200) return false;
  const parts = cookieValue.split(".");
  if (parts.length !== 2) return false;
  try {
    const payload = JSON.parse(new TextDecoder().decode(fromBase64url(parts[0]))) as {
      v?: unknown; u?: unknown; s?: unknown; iat?: unknown;
    };
    if (payload.v !== 1 || payload.u !== identity.userId || payload.s !== identity.sessionId ||
      typeof payload.iat !== "number" || !Number.isSafeInteger(payload.iat) ||
      payload.iat > now || now - payload.iat >= PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS * 1000) return false;
    const signature = fromBase64url(parts[1]);
    if (signature.length !== 32) return false;
    return crypto.subtle.verify("HMAC", await keyFor(secret), signature, encoder.encode(parts[0]));
  } catch {
    return false;
  }
}
