"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { getSiteUrl } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { safeRelativePath } from "@/lib/auth";
import { getDb } from "@/db";
import { studentProfiles } from "@/db/schema";

const passwordSchema = z
  .string()
  .min(12, "Use at least 12 characters for your password.")
  .max(72, "Your password must be 72 characters or fewer.")
  .regex(/[a-z]/, "Add at least one lowercase letter.")
  .regex(/[A-Z]/, "Add at least one uppercase letter.")
  .regex(/[0-9]/, "Add at least one number.")
  .regex(/[^A-Za-z0-9]/, "Add at least one symbol.");

const registrationSchema = z
  .object({
    firstName: z.string().trim().min(2).max(80),
    lastName: z.string().trim().min(2).max(80),
    email: z.string().trim().toLowerCase().email(),
    mobile: z
      .string()
      .trim()
      .regex(/^\+?[0-9 ()-]{7,24}$/, "Enter a valid mobile number."),
    province: z.string().trim().min(2).max(60),
    institution: z.string().trim().min(2).max(120),
    academicLevel: z.string().trim().min(2).max(80),
    password: passwordSchema,
    confirmPassword: z.string(),
    termsAccepted: z.literal(true, {
      message: "Accept the Terms and Privacy Policy to register.",
    }),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ["confirmPassword"],
    message: "The passwords do not match.",
  });

const loginSchema = z.object({
  email: z.string().trim().toLowerCase().email(),
  password: z.string().min(1),
  next: z.string().optional(),
});

export async function registerAction(formData: FormData) {
  const parsed = registrationSchema.safeParse({
    firstName: formData.get("firstName"),
    lastName: formData.get("lastName"),
    email: formData.get("email"),
    mobile: formData.get("mobile"),
    province: formData.get("province"),
    institution: formData.get("institution"),
    academicLevel: formData.get("academicLevel"),
    password: formData.get("password"),
    confirmPassword: formData.get("confirmPassword"),
    termsAccepted: formData.get("terms") === "on",
  });

  if (!parsed.success) {
    redirectWithMessage(
      "/register",
      "error",
      parsed.error.issues[0]?.message ?? "Check your registration details.",
    );
  }

  const values = parsed.data;
  const verificationPath = `/verify-email?email=${encodeURIComponent(values.email)}&registered=1`;
  let result;
  try {
    const supabase = await createSupabaseServerClient();
    result = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
      options: {
        emailRedirectTo: `${getSiteUrl()}/login?verified=1`,
        data: {
          first_name: values.firstName,
          last_name: values.lastName,
          mobile: values.mobile,
          province: values.province,
          institution: values.institution,
          academic_level: values.academicLevel,
          terms_accepted_at: new Date().toISOString(),
        },
      },
    });
  } catch {
    // Never log submitted details, passwords, tokens or raw provider errors.
    console.error("student_registration_failed", { code: "auth_unavailable" });
    redirectWithMessage("/register", "error", "Registration is temporarily unavailable. Please try again shortly. If you already registered, log in or reset your password.");
  }

  const { data, error } = result;

  if (error) {
    // Match the neutral success response: do not disclose account existence.
    if (error.code === "user_already_exists" || error.code === "email_exists") {
      redirect(verificationPath);
    }
    console.error("student_registration_failed", { code: safeAuthErrorCode(error.code), status: error.status });
    redirectWithMessage(
      "/register",
      "error",
      registrationErrorMessage(error.code),
    );
  }

  if (!data.user) {
    console.error("student_registration_failed", { code: "missing_user" });
    redirectWithMessage("/register", "error", "Registration could not be completed. Please try again shortly or contact us for help.");
  }

  // Supabase creates the authoritative profile in its auth.users trigger.
  // Only mirror an authenticated, verified identity. Duplicate signup can
  // return an obfuscated user, and unverified retries must not overwrite names.
  if (data.session && data.user.email_confirmed_at) {
    try {
      await getDb()
        .insert(studentProfiles)
        .values({
          userId: data.user.id,
          email: values.email,
          displayName: `${values.firstName} ${values.lastName}`,
        })
        .onConflictDoUpdate({
          target: studentProfiles.userId,
          set: {
            email: values.email,
            displayName: `${values.firstName} ${values.lastName}`,
            updatedAt: new Date().toISOString(),
          },
        });
    } catch {
      // Authentication remains available if the non-critical profile mirror is delayed.
    }
  }

  if (data.session && data.user?.email_confirmed_at) {
    redirect("/dashboard?registered=1");
  }

  redirect(verificationPath);
}

export async function verifyEmailAction(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const token = String(formData.get("token") ?? "").replace(/\s/g, "");

  if (!z.string().email().safeParse(email).success || !/^\d{6}$/.test(token)) {
    redirect(
      `/verify-email?email=${encodeURIComponent(email)}&error=${encodeURIComponent("Enter the six-digit code from your email.")}`,
    );
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.verifyOtp({
    email,
    token,
    type: "email",
  });

  if (error) {
    redirect(
      `/verify-email?email=${encodeURIComponent(email)}&error=${encodeURIComponent("This verification code is no longer active. If you already used the confirmation link, your email is verified — log in to continue. Otherwise, request a new verification email.")}`,
    );
  }

  redirect("/dashboard?verified=1");
}

export async function resendVerificationAction(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  if (!z.string().email().safeParse(email).success) {
    redirectWithMessage(
      "/verify-email",
      "error",
      "Enter the email address used for registration.",
    );
  }

  let result;
  try {
    const supabase = await createSupabaseServerClient();
    result = await supabase.auth.resend({
      type: "signup",
      email,
      options: {
        emailRedirectTo: `${getSiteUrl()}/login?verified=1`,
      },
    });
  } catch {
    console.error("student_verification_resend_failed", { code: "auth_unavailable" });
    redirect(`/verify-email?email=${encodeURIComponent(email)}&error=${encodeURIComponent("Verification email could not be requested. Please try again shortly or contact us for help.")}`);
  }
  const { error } = result;

  if (error) {
    console.error("student_verification_resend_failed", { code: safeAuthErrorCode(error.code), status: error.status });
    redirect(`/verify-email?email=${encodeURIComponent(email)}&error=${encodeURIComponent(registrationErrorMessage(error.code))}`);
  }

  redirect(
    `/verify-email?email=${encodeURIComponent(email)}&resent=1`,
  );
}

export async function loginAction(formData: FormData) {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    next: String(formData.get("next") ?? ""),
  });
  if (!parsed.success) {
    redirectWithMessage(
      "/login",
      "error",
      "Enter a valid email address and password.",
    );
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: parsed.data.email,
    password: parsed.data.password,
  });

  if (error) {
    if (/rate limit|too many/i.test(error.message)) redirect("/errors/429");
    if (/email not confirmed/i.test(error.message)) {
      redirect(
        `/verify-email?email=${encodeURIComponent(parsed.data.email)}&error=${encodeURIComponent("Verify your email before logging in.")}`,
      );
    }
    redirectWithMessage(
      "/login",
      "error",
      "The email or password is incorrect. Please try again.",
    );
  }

  redirect(safeRelativePath(parsed.data.next));
}

export async function googleAuthAction(formData: FormData) {
  const next = safeRelativePath(String(formData.get("next") ?? "/dashboard"));
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${getSiteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error || !data.url) {
    console.error("student_google_auth_failed", {
      code: safeAuthErrorCode(error?.code),
      status: error?.status,
    });
    redirectWithMessage(
      "/login",
      "error",
      "Google sign-in is temporarily unavailable. Please use your email and password or try again shortly.",
    );
  }

  redirect(data.url);
}

export async function linkedInAuthAction(formData: FormData) {
  const next = safeRelativePath(String(formData.get("next") ?? "/dashboard"));
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "linkedin_oidc",
    options: {
      redirectTo: `${getSiteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error || !data.url) {
    console.error("student_linkedin_auth_failed", {
      code: safeAuthErrorCode(error?.code),
      status: error?.status,
    });
    redirectWithMessage(
      "/login",
      "error",
      "LinkedIn sign-in is temporarily unavailable. Please use Google, email and password, or try again shortly.",
    );
  }

  redirect(data.url);
}

export async function facebookAuthAction(formData: FormData) {
  const next = safeRelativePath(String(formData.get("next") ?? "/dashboard"));
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "facebook",
    options: {
      redirectTo: `${getSiteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error || !data.url) {
    console.error("student_facebook_auth_failed", {
      code: safeAuthErrorCode(error?.code),
      status: error?.status,
    });
    redirectWithMessage(
      "/login",
      "error",
      "Facebook sign-in is temporarily unavailable. Please use Google, LinkedIn, GitHub, email and password, or try again shortly.",
    );
  }

  redirect(data.url);
}

export async function githubAuthAction(formData: FormData) {
  const next = safeRelativePath(String(formData.get("next") ?? "/dashboard"));
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "github",
    options: {
      redirectTo: `${getSiteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error || !data.url) {
    console.error("student_github_auth_failed", {
      code: safeAuthErrorCode(error?.code),
      status: error?.status,
    });
    redirectWithMessage(
      "/login",
      "error",
      "GitHub sign-in is temporarily unavailable. Please use Google, LinkedIn, Facebook, email and password, or try again shortly.",
    );
  }

  redirect(data.url);
}

export async function forgotPasswordAction(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  if (!z.string().email().safeParse(email).success) {
    redirectWithMessage(
      "/forgot-password",
      "error",
      "Enter a valid email address.",
    );
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${getSiteUrl()}/auth/confirm?next=/reset-password`,
  });

  if (error) {
    if (/rate limit|too many/i.test(error.message)) {
      redirect("/errors/429");
    }
    redirectWithMessage(
      "/forgot-password",
      "error",
      "We could not request a reset email right now. Please try again.",
    );
  }

  // The same response is shown whether the account exists or not.
  redirect("/forgot-password?sent=1");
}

export async function resetPasswordAction(formData: FormData) {
  const password = String(formData.get("password") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");
  const parsed = passwordSchema.safeParse(password);

  if (!parsed.success) {
    redirectWithMessage(
      "/reset-password",
      "error",
      parsed.error.issues[0]?.message ?? "Choose a stronger password.",
    );
  }
  if (password !== confirmPassword) {
    redirectWithMessage(
      "/reset-password",
      "error",
      "The passwords do not match.",
    );
  }

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    redirectWithMessage(
      "/forgot-password",
      "error",
      "That reset link has expired. Request a new one.",
    );
  }

  const { error } = await supabase.auth.updateUser({ password });
  if (error) {
    redirectWithMessage(
      "/reset-password",
      "error",
      friendlyAuthError(error.message, "We could not update your password."),
    );
  }

  await supabase.auth.signOut({ scope: "global" });
  redirect("/login?password_updated=1");
}

export async function signOutAction() {
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut({ scope: "local" });
  redirect("/login?signed_out=1");
}

function friendlyAuthError(message: string, fallback: string): string {
  if (/password/i.test(message)) return message;
  if (/rate limit|too many/i.test(message)) {
    return "Too many attempts. Wait a few minutes before trying again.";
  }
  return fallback;
}

function registrationErrorMessage(code: string | undefined): string {
  switch (code) {
    case "over_email_send_rate_limit":
    case "over_request_rate_limit":
      return "Too many attempts. Wait a few minutes before trying again. If a verification email already arrived, use its code or link.";
    case "weak_password":
      return "Choose a stronger password with at least 12 characters, uppercase, lowercase, a number and a symbol. Avoid common or previously exposed passwords.";
    case "email_address_invalid":
      return "Check your email address and try again.";
    case "email_address_not_authorized":
      return "Verification email delivery is unavailable for this address. Please contact us for help.";
    case "signup_disabled":
      return "New registrations are temporarily unavailable. Please contact us for help.";
    default:
      return "Registration or verification could not be completed. Please try again shortly. If you already registered, log in or reset your password. Contact us if this continues.";
  }
}

function safeAuthErrorCode(code: string | undefined): string {
  return code && /^[a-z_]{1,64}$/.test(code) ? code : "unknown_auth_error";
}

function redirectWithMessage(path: string, key: string, message: string): never {
  redirect(`${path}?${key}=${encodeURIComponent(message)}`);
}
