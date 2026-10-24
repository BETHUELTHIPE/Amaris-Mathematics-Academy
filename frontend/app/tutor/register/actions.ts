"use server";

import { parseLocation } from "@/lib/location-server";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getSiteUrl } from "@/lib/supabase/config";

const password = z.string().min(12).max(72).regex(/[a-z]/).regex(/[A-Z]/).regex(/[0-9]/).regex(/[^A-Za-z0-9]/);
const registration = z.object({
  firstName: z.string().trim().min(2).max(80), lastName: z.string().trim().min(2).max(80),
  email: z.string().trim().email(), password, confirmPassword: z.string(), consent: z.literal(true),
}).refine(values => values.password === values.confirmPassword);
function verification(email: string, key: string, value = "1"): never {
  redirect(`/tutor/verify-email?email=${encodeURIComponent(email)}&${key}=${encodeURIComponent(value)}`);
}
export async function registerApplicant(form: FormData): Promise<never> {
  const location = await parseLocation(Object.fromEntries(form));
  if (!location.value) redirect("/tutor/register?error=" + encodeURIComponent(Object.values(location.errors)[0] || "Please choose your location."));
  const parsed = registration.safeParse({ ...Object.fromEntries(form), consent: form.get("consent") === "on" });
  if (!parsed.success) redirect("/tutor/register?error=Check+your+name,+email,+password+and+privacy+agreement.");
  const values = parsed.data;
  let failed = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.signUp({
      email: values.email.trim().toLowerCase(), password: values.password,
      options: {
        emailRedirectTo: `${getSiteUrl()}/auth/confirm?next=/tutor/apply`,
        data: { first_name: values.firstName, last_name: values.lastName, ...location.value, terms_accepted_at: new Date().toISOString() },
      },
    });
    failed = Boolean(error && !["user_already_exists", "email_exists"].includes(error.code || ""));
  } catch { failed = true; }
  if (failed) redirect("/tutor/register?error=Registration+could+not+be+completed.+Please+retry+shortly,+or+sign+in+if+already+registered.");
  // Same response for existing/new identities. Registration never grants tutor permissions.
  verification(values.email, "requested");
}
export async function verifyApplicant(form: FormData): Promise<never> {
  const email = String(form.get("email") || "").trim();
  const token = String(form.get("token") || "").trim();
  if (!z.string().email().safeParse(email).success || !/^\d{6}$/.test(token)) verification(email, "error", "Enter your email and six-digit code.");
  let failed = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.verifyOtp({ email, token, type: "signup" });
    failed = Boolean(error);
  } catch { failed = true; }
  if (failed) verification(email, "error", "That code is invalid or expired. Request a new code or try again shortly.");
  redirect("/tutor/apply");
}
export async function resendApplicantVerification(form: FormData): Promise<never> {
  const email = String(form.get("email") || "").trim();
  if (!z.string().email().safeParse(email).success) verification(email, "error", "Enter your registration email.");
  let failed = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.resend({ type: "signup", email, options: { emailRedirectTo: `${getSiteUrl()}/auth/confirm?next=/tutor/apply` } });
    failed = Boolean(error);
  } catch { failed = true; }
  if (failed) verification(email, "error", "A code could not be requested. Please retry shortly or sign in if already verified.");
  verification(email, "requested");
}
export async function loginApplicant(form: FormData): Promise<never> {
  const email = String(form.get("email") || "").trim().toLowerCase();
  const secret = String(form.get("password") || "");
  if (!z.string().email().safeParse(email).success || !secret) redirect("/tutor/apply/login?error=Enter+your+email+and+password.");
  let failed = false;
  let unverified = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.auth.signInWithPassword({ email, password: secret });
    failed = Boolean(error || !data.user);
    unverified = error?.code === "email_not_confirmed";
  } catch { failed = true; }
  if (unverified) verification(email, "error", "Verify your email before applying.");
  if (failed) redirect("/tutor/apply/login?error=Sign-in+could+not+be+completed.+Check+your+details+or+retry+shortly.");
  redirect("/tutor/apply");
}
