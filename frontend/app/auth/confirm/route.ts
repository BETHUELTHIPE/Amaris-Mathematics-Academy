import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { safeRelativePath } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";

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
  const next = safeRelativePath(searchParams.get("next"));
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

  if (error) {
    const url = new URL("/login", request.url);
    url.searchParams.set(
      "error",
      "This email link is invalid or has expired. Please request a new one.",
    );
    return NextResponse.redirect(url);
  }

  return NextResponse.redirect(new URL(next, request.url));
}
