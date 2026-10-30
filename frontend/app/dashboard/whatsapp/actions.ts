"use server";

import { getStudentWhatsAppPreference, setStudentWhatsAppPreference } from "@/lib/student-api";

export async function saveWhatsAppPreference(_prev: { message: string; error: boolean }, form: FormData) {
  const optedIn = form.get("opted_in") === "on";
  const number = String(form.get("number") || "").trim();
  try {
    if (optedIn && !/^\+[1-9][0-9]{7,14}$/.test(number)) {
      return { message: "Enter a valid international number, e.g. +27821234567.", error: true };
    }
    await setStudentWhatsAppPreference({ number, opted_in: optedIn });
    return { message: optedIn ? "WhatsApp notifications enabled." : "WhatsApp notifications disabled.", error: false };
  } catch {
    return { message: "Unable to save your preference. Please try again.", error: true };
  }
}
