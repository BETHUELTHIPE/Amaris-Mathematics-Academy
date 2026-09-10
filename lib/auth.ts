import type { User } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { getSupabaseConfig } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type StudentIdentity = {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  displayName: string;
  emailVerified: boolean;
};

export async function getStudentIdentity(): Promise<StudentIdentity | null> {
  if (!getSupabaseConfig()) return null;

  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) return null;
  return mapUser(user);
}

export async function requireVerifiedStudent(
  returnTo = "/dashboard",
): Promise<StudentIdentity> {
  const student = await getStudentIdentity();
  if (!student) {
    redirect(`/login?next=${encodeURIComponent(safeRelativePath(returnTo))}`);
  }
  if (!student.emailVerified) {
    redirect(`/verify-email?email=${encodeURIComponent(student.email)}`);
  }
  return student;
}

export function safeRelativePath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/dashboard";
  }

  let url: URL;
  try {
    url = new URL(value, "https://app.local");
  } catch {
    return "/dashboard";
  }

  if (url.origin !== "https://app.local") return "/dashboard";
  if (
    [
      "/login",
      "/register",
      "/forgot-password",
      "/reset-password",
      "/verify-email",
      "/session-expired",
    ].includes(url.pathname) ||
    url.pathname.startsWith("/auth/")
  ) {
    return "/dashboard";
  }

  return `${url.pathname}${url.search}${url.hash}`;
}

function mapUser(user: User): StudentIdentity {
  const firstName = cleanName(user.user_metadata?.first_name) || "Student";
  const lastName = cleanName(user.user_metadata?.last_name);
  return {
    id: user.id,
    email: user.email ?? "",
    firstName,
    lastName,
    displayName: [firstName, lastName].filter(Boolean).join(" "),
    emailVerified: Boolean(user.email_confirmed_at),
  };
}

function cleanName(value: unknown): string {
  return typeof value === "string" ? value.trim().slice(0, 80) : "";
}
