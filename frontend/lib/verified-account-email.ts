/**
 * Shared, fail-closed email ownership gate for every Amaris account type.
 *
 * Email confirmation is required in addition to the normal password/OAuth/OTP
 * exchange. The authoritative Supabase Auth user record is checked server-side,
 * not an untrusted JWT metadata flag or a browser field. Unverified and
 * unverifiable sessions are cleared locally before redirecting to verification.
 * Approval for tutor or future sponsor roles is a separate authorization step.
 */
type VerifiedEmailUser = { email_confirmed_at?: string | null };
type EmailVerificationAuth = {
  getUser(): Promise<{ data: { user: VerifiedEmailUser | null }; error: unknown }>;
  signOut(options: { scope: "local" }): Promise<unknown>;
};

export async function hasVerifiedAccountEmail(auth: EmailVerificationAuth): Promise<boolean> {
  try {
    const { data, error } = await auth.getUser();
    if (!error && Boolean(data.user?.email_confirmed_at)) return true;
  } catch {
    // Network errors must never turn an unverified identity into an authenticated user.
  }

  try {
    await auth.signOut({ scope: "local" });
  } catch {
    // Fail closed even if the client's local cookies cannot be cleared.
  }
  return false;
}
