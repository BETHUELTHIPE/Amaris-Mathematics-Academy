"use server";

import { submitStudentFeedback } from "@/lib/student-api";

export async function sendHappyForm(formData: FormData) {
  const service = String(formData.get("service") ?? "");
  const service_reference = String(formData.get("reference") ?? "").trim();
  const overall_rating = Number(formData.get("overall_rating"));
  const tutor_rating_value = String(formData.get("tutor_rating") ?? "");
  const tutor_rating = tutor_rating_value ? Number(tutor_rating_value) : null;
  const comments = String(formData.get("comments") ?? "").trim();
  if (!["live_class", "course"].includes(service) || !service_reference || !Number.isInteger(overall_rating) || overall_rating < 1 || overall_rating > 5 || (tutor_rating !== null && (!Number.isInteger(tutor_rating) || tutor_rating < 1 || tutor_rating > 5)) || comments.length > 1000) {
    return { ok: false, message: "Please check the required fields and ratings." };
  }
  try {
    await submitStudentFeedback({ service, service_reference, overall_rating, tutor_rating: service === "live_class" ? tutor_rating : null, comments });
    return { ok: true, message: "Thank you! Your feedback has been submitted." };
  } catch {
    return { ok: false, message: "We could not submit your feedback. Please check the service reference or try again." };
  }
}
