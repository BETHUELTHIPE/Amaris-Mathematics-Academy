/**
 * A reset email may grant only a short-lived password recovery destination.
 * Ordinary sign-in, signup, and OAuth callbacks must never open this route.
 */
export const PASSWORD_RECOVERY_COOKIE = "amaris-password-recovery";
export const PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS = 15 * 60;

export function isPasswordRecoveryCallback(
  destination: string | null,
  flow: string | null,
  type: string | null,
): boolean {
  return destination === "/reset-password" &&
    (flow === "password-recovery" || type === "recovery");
}
