import "server-only";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Booking identity is always taken from the authenticated Supabase account,
 * never from query parameters or client-submitted name fields.
 */
export type RegisteredBookingName = {
  firstName: string;
  lastName: string;
  fullName: string;
};

function cleanName(value: unknown): string {
  return typeof value === "string" ? value.trim().replace(/\s+/g, " ").slice(0, 80) : "";
}

export function registeredBookingName(
  metadata: Record<string, unknown> | null | undefined,
): RegisteredBookingName | null {
  if (!metadata) return null;
  const fullName = cleanName(metadata.full_name) || cleanName(metadata.name);
  const names = fullName.split(" ").filter(Boolean);
  const firstName = cleanName(metadata.first_name) || cleanName(metadata.given_name) || names[0] || "";
  const lastName = cleanName(metadata.last_name) || cleanName(metadata.family_name) || names.slice(1).join(" ");
  if (firstName.length < 2 || lastName.length < 2) return null;
  if (firstName.toLowerCase() === "student" && lastName.toLowerCase() === "learner") return null;
  return { firstName, lastName, fullName: `${firstName} ${lastName}` };
}

export async function getVerifiedStudentBookingName(
  expectedAccountId: string,
): Promise<RegisteredBookingName | null> {
  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.auth.getUser();
    const user = data.user;
    if (error || !user || user.id !== expectedAccountId || !user.email_confirmed_at) return null;
    return registeredBookingName(user.user_metadata);
  } catch {
    return null; // Fail closed: checkout cannot create a hold with unverified identity.
  }
}
