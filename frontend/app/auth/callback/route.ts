import { NextResponse, type NextRequest } from "next/server";
import { isStudentProfileComplete, safeRelativePath } from "@/lib/auth";
import { getSiteUrl } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const next = safeRelativePath(request.nextUrl.searchParams.get("next"));

  if (!code) {
    return redirectToLogin("Google registration could not be completed. Please try again.");
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error("student_google_callback_failed", {
      code: typeof error.code === "string" ? error.code : "oauth_exchange_failed",
      status: error.status,
    });
    return redirectToLogin("Google registration could not be completed. Please try again.");
  }

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user?.email_confirmed_at) {
    return redirectToLogin("Google registration could not be verified. Please try again.");
  }

  const { data: profile, error: profileError } = await supabase
    .from("student_profiles")
    .select("first_name,last_name,mobile,province,institution,academic_level")
    .eq("id", user.id)
    .maybeSingle();

  if (profileError || !profile || !isStudentProfileComplete(profile)) {
    if (profileError) {
      console.error("student_google_profile_check_failed", {
        code: typeof profileError.code === "string" ? profileError.code : "profile_check_failed",
      });
    }
    const completionUrl = new URL("/complete-profile", getSiteUrl());
    completionUrl.searchParams.set("next", next);
    return NextResponse.redirect(completionUrl);
  }

  return NextResponse.redirect(new URL(next, getSiteUrl()));
}

function redirectToLogin(message: string) {
  const url = new URL("/login", getSiteUrl());
  url.searchParams.set("error", message);
  return NextResponse.redirect(url);
}
