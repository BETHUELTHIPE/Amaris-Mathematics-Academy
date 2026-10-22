"use server";

import { resolveCurriculumFields } from "@/lib/school-curriculum.mjs";
import { redirect } from "next/navigation";
import { createTutorSlot, TutorApiError, updateTutorSlot, type SlotInput } from "@/lib/tutor-api";
import { createSupabaseServerClient } from "@/lib/supabase/server";

function cleanStart(value: string): string {
  // Native datetime-local fields have no timezone. Amaris sessions use SAST (UTC+02:00).
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error("Enter a valid start date and time.");
  const date = new Date(`${value}:00+02:00`);
  if (Number.isNaN(date.getTime())) throw new Error("Enter a valid start date and time.");
  return date.toISOString();
}

function slotInput(form: FormData): SlotInput {
  const { programme, subject, level } = resolveCurriculumFields(form, false);
  const duration = Number(form.get("duration_hours"));
  const zoom = String(form.get("zoom_join_url") || "").trim().slice(0, 200);
  if (!["caps", "ieb", "tvet", "university"].includes(programme)) throw new Error("Choose a programme.");
  if (!["mathematics", "mathematical_literacy"].includes(subject)) throw new Error("Choose a subject.");
  if (level.length < 2) throw new Error("Enter the grade or academic level.");
  if (!Number.isInteger(duration) || duration < 1 || duration > 24) {
    throw new Error("Choose between 1 and 24 whole hours.");
  }
  if (!zoom.startsWith("https://")) throw new Error("Enter a secure Zoom meeting link.");
  return {
    programme,
    subject,
    level,
    starts_at: cleanStart(String(form.get("starts_at") || "")),
    duration_hours: duration,
    zoom_join_url: zoom,
    is_active: form.get("is_active") === "on",
  };
}

function failureMessage(error: unknown): string {
  return error instanceof TutorApiError || error instanceof Error
    ? error.message.slice(0, 180)
    : "Unable to save the session.";
}

function go(message: string, kind: "success" | "error") {
  redirect(`/tutor/dashboard?${kind}=${encodeURIComponent(message)}`);
}

export async function createTutorSlotAction(form: FormData): Promise<void> {
  let errorMessage = "";
  try {
    await createTutorSlot(slotInput(form));
  } catch (error) {
    errorMessage = failureMessage(error);
  }
  if (errorMessage) go(errorMessage, "error");
  go("Your tutor availability has been published.", "success");
}

export async function updateTutorSlotAction(form: FormData): Promise<void> {
  let errorMessage = "";
  const id = Number(form.get("slot_id"));
  if (!Number.isSafeInteger(id) || id <= 0) go("Invalid tutor slot.", "error");
  try {
    await updateTutorSlot(id, slotInput(form));
  } catch (error) {
    errorMessage = failureMessage(error);
  }
  if (errorMessage) go(errorMessage, "error");
  go("Your session has been updated.", "success");
}

export async function pauseTutorSlotAction(form: FormData): Promise<void> {
  let errorMessage = "";
  const id = Number(form.get("slot_id"));
  if (!Number.isSafeInteger(id) || id <= 0) go("Invalid tutor slot.", "error");
  try {
    await updateTutorSlot(id, { is_active: false });
  } catch (error) {
    errorMessage = failureMessage(error);
  }
  if (errorMessage) go(errorMessage, "error");
  go("Your availability has been paused.", "success");
}

export async function tutorLoginAction(form: FormData): Promise<void> {
  const email = String(form.get("email") || "").trim().toLowerCase();
  const password = String(form.get("password") || "");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !password) {
    redirect("/tutor/login?error=credentials");
  }
  let credentialsInvalid = false;
  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    credentialsInvalid = Boolean(error);
  } catch {
    redirect("/tutor/login?error=unavailable");
  }
  if (credentialsInvalid) redirect("/tutor/login?error=credentials");
  redirect("/tutor/dashboard");
}
