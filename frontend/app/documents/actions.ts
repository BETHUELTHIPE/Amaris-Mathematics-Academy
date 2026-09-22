"use server";

import { redirect } from "next/navigation";
import {
  isStudentFileCategory,
  uploadStudentFile,
} from "@/lib/student-storage";

export async function uploadStudentDocumentAction(formData: FormData) {
  const categoryValue = String(formData.get("category") ?? "uploads");
  const file = formData.get("file");

  if (!isStudentFileCategory(categoryValue)) {
    redirect("/documents?error=Choose+a+valid+document+category.");
  }

  if (!(file instanceof File) || file.size <= 0) {
    redirect("/documents?error=Choose+a+file+before+uploading.");
  }

  try {
    await uploadStudentFile(file, categoryValue);
  } catch (error) {
    const message = error instanceof Error ? error.message : "The upload could not be completed.";
    redirect(`/documents?error=${encodeURIComponent(message)}`);
  }

  redirect("/documents?uploaded=1");
}
