import type { User } from "@supabase/supabase-js";
import { cache } from "react";
import { redirect } from "next/navigation";
import { getSupabaseConfig } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

declare const __E2E_SYNTHETIC_STUDENT__: boolean;

export type StudentIdentity = {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  displayName: string;
  emailVerified: boolean;
};

function getSyntheticE2EStudent(): StudentIdentity | null {
  if (!__E2E_SYNTHETIC_STUDENT__) return null;
  return {
    id: "00000000-0000-4000-8000-000000000001",
    email: "responsive.student@example.test",
    firstName: "Responsive",
    lastName: "Student",
    displayName: "Responsive Student",
    emailVerified: true,
  };
}

export const getStudentIdentity = cache(async (): Promise<StudentIdentity | null> => {
  const syntheticStudent = getSyntheticE2EStudent();
  if (syntheticStudent) return syntheticStudent;
  if (!getSupabaseConfig()) return null;

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getUser();

  if (error || !data?.user) return null;
  return mapUser(data.user);
});

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
  const metadata = user.user_metadata ?? {};
  const firstName = cleanName(metadata.first_name) || "Student";
  const lastName = cleanName(metadata.last_name);
  return {
    id: user.id,
    email: user.email ?? "",
    firstName,
    lastName,
    displayName: [firstName, lastName].filter(Boolean).join(" "),
    emailVerified: Boolean(user.email && user.email_confirmed_at && !user.is_anonymous),
  };
}

function cleanName(value: unknown): string {
  return typeof value === "string" ? value.trim().slice(0, 80) : "";
}
