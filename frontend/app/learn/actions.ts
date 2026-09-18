"use server";

import { redirect } from "next/navigation";
import { saveStudentProgress } from "@/lib/student-api";

export async function saveLessonProgressAction(formData: FormData) {
  const courseSlug = String(formData.get("courseSlug") ?? "");
  const lessonSlug = String(formData.get("lessonSlug") ?? "");
  const positionSeconds = Math.max(0, Number(formData.get("positionSeconds") ?? 0) || 0);
  const progressPercent = Math.min(100, Math.max(0, Number(formData.get("progressPercent") ?? 0) || 0));

  await saveStudentProgress({ courseSlug, lessonSlug, positionSeconds, progressPercent });
  redirect("/dashboard?progress_saved=1");
}
