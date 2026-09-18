"use server";

import { revalidatePath } from "next/cache";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";

export async function saveProgressAction(formData: FormData) {
  const courseSlug = String(formData.get("courseSlug") ?? "").trim();
  const lessonSlug = String(formData.get("lessonSlug") ?? "").trim();
  const position = Number.parseInt(String(formData.get("positionSeconds") ?? "0"), 10);
  const completed = String(formData.get("completed") ?? "") === "true";

  if (!/^[a-z0-9-]{2,200}$/i.test(courseSlug) || !/^[a-z0-9-]{1,200}$/i.test(lessonSlug)) {
    return;
  }
  await requireVerifiedStudent(`/learn/${courseSlug}/${lessonSlug}`);
  await studentApi(`/student/courses/${encodeURIComponent(courseSlug)}/progress/`, {
    method: "PUT",
    body: JSON.stringify({
      lesson_slug: lessonSlug,
      position_seconds: Number.isFinite(position) ? Math.max(0, position) : 0,
      completed,
    }),
  });
  revalidatePath("/dashboard");
  revalidatePath(`/learn/${courseSlug}/${lessonSlug}`);
}
