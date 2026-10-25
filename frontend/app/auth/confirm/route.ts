import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { safeRelativePath } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { hasVerifiedAccountEmail } from "@/lib/verified-account-email";
import { isPasswordRecoveryCallback, PASSWORD_RECOVERY_COOKIE, PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS } from "@/lib/password-recovery";

const allowedOtpTypes = new Set<EmailOtpType>([
  "signup",
  "recovery",
  "email",
  "email_change",
  "invite",
  "magiclink",
]);

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const suppliedType = searchParams.get("type") as EmailOtpType | null;
  const recovery = isPasswordRecoveryCallback(searchParams.get("next"), searchParams.get("flow"), suppliedType);
  const next = recovery ? "/reset-password" : safeRelativePath(searchParams.get("next"));
  const supabase = await createSupabaseServerClient();

  let error: Error | null = null;
  if (code) {
    ({ error } = await supabase.auth.exchangeCodeForSession(code));
  } else if (
    tokenHash &&
    suppliedType &&
    allowedOtpTypes.has(suppliedType)
  ) {
    ({ error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: suppliedType,
    }));
  } else {
    error = new Error("Missing confirmation token");
  }

  // Even a valid confirmation or recovery link cannot open private pages
  // until Supabase reports that the user's email address is confirmed.
  if (!error && !(await hasVerifiedAccountEmail(supabase.auth))) {
    error = new Error("Email verification required");
  }

  if (error) {
    const url = new URL("/login", request.url);
    url.searchParams.set(
      "error",
      "This email link is invalid or has expired. Please request a new one.",
    );
    return NextResponse.redirect(url);
  }

  const response = NextResponse.redirect(new URL(next, request.url));
  if (recovery) {
    // Server-only, short-lived proof that Supabase accepted this recovery link.
    response.cookies.set(PASSWORD_RECOVERY_COOKIE, "1", {
      httpOnly: true,
      secure: request.nextUrl.protocol === "https:",
      sameSite: "lax",
      path: "/reset-password",
      maxAge: PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS,
    });
  }
  return response;
}
