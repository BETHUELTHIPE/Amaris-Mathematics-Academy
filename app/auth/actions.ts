"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { getSiteUrl } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { safeRelativePath } from "@/lib/auth";

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
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signUp({
    email: values.email,
    password: values.password,
    options: {
      emailRedirectTo: `${getSiteUrl()}/auth/confirm?next=/dashboard`,
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

  if (error) {
    redirectWithMessage(
      "/register",
      "error",
      friendlyAuthError(error.message, "We could not create your profile."),
    );
  }

  if (data.session && data.user?.email_confirmed_at) {
    redirect("/dashboard?registered=1");
  }

  redirect(
    `/verify-email?email=${encodeURIComponent(values.email)}&registered=1`,
  );
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
    type: "signup",
  });

  if (error) {
    redirect(
      `/verify-email?email=${encodeURIComponent(email)}&error=${encodeURIComponent("That code is invalid or has expired. Request a new code and try again.")}`,
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

  const supabase = await createSupabaseServerClient();
  await supabase.auth.resend({
    type: "signup",
    email,
    options: {
      emailRedirectTo: `${getSiteUrl()}/auth/confirm?next=/dashboard`,
    },
  });

  redirect(
    `/verify-email?email=${encodeURIComponent(email)}&resent=1`,
  );
}

export async function loginAction(formData: FormData) {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    next: formData.get("next"),
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
  await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${getSiteUrl()}/auth/confirm?next=/reset-password`,
  });

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

function redirectWithMessage(path: string, key: string, message: string): never {
  redirect(`${path}?${key}=${encodeURIComponent(message)}`);
}
