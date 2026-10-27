"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { requireVerifiedStudent } from "@/lib/auth";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { registeredBookingName } from "@/lib/registered-booking-name";

const component = z.string().trim().min(2).max(80)
  .regex(/^[\p{L}\p{M}][\p{L}\p{M}\s'’-]*$/u, "Use your actual first or last name (letters only).");

const profileSchema = z.object({
  firstName: component,
  lastName: component,
});

function rejected(message: string): never {
  redirect(`/account/complete-profile?error=${encodeURIComponent(message)}`);
}

/**
 * A verified student may complete their OWN verified Supabase Auth profile.
 * Never accept a user ID, email, payment name, or role from a form.
 * Django's authenticated student record synchronizes legacy placeholder
 * names from this authoritative user record before any PayFast hold.
 */
export async function completeStudentBookingProfile(form: FormData): Promise<never> {
  const identity = await requireVerifiedStudent("/account/complete-profile");
  const parsed = profileSchema.safeParse({
    firstName: form.get("firstName"),
    lastName: form.get("lastName"),
  });
  if (!parsed.success) rejected("Enter your actual first and last names, at least two letters each.");
  const { firstName, lastName } = parsed.data;
  if (!registeredBookingName({ first_name: firstName, last_name: lastName })) {
    rejected("A generic or incomplete name cannot be used for a booking.");
  }

  let failed = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { data: original, error: readError } = await supabase.auth.getUser();
    if (readError || !original.user || original.user.id !== identity.id ||
        !original.user.email_confirmed_at) {
      failed = true;
    } else {
      const { error: updateError } = await supabase.auth.updateUser({
        data: { first_name: firstName, last_name: lastName },
      });
      if (updateError) {
        failed = true;
      } else {
        const { data: verified, error: verifyError } = await supabase.auth.getUser();
        const updatedName = registeredBookingName(verified.user?.user_metadata);
        if (verifyError || !verified.user || verified.user.id !== identity.id ||
            !verified.user.email_confirmed_at ||
            updatedName?.firstName !== firstName || updatedName.lastName !== lastName) {
          failed = true;
        }
      }
    }
  } catch {
    failed = true;
  }

  if (failed) rejected("Unable to save your verified profile. Please try again or contact Amaris support.");
  redirect("/book-online-live-class?profile=completed");
}
