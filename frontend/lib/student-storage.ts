import { createSupabaseServerClient } from "@/lib/supabase/server";
import { requireVerifiedStudent } from "@/lib/auth";

export const STUDENT_STORAGE_BUCKET = "Amaris Mathematics Academy";
export const STUDENT_STORAGE_MAX_BYTES = 50 * 1024 * 1024;

export const STUDENT_FILE_CATEGORIES = [
  "invoices",
  "receipts",
  "certificates",
  "reports",
  "letters",
  "resources",
  "uploads",
] as const;

export type StudentFileCategory = (typeof STUDENT_FILE_CATEGORIES)[number];

export type StudentStoredFile = {
  category: StudentFileCategory;
  name: string;
  path: string;
  size: number | null;
  mimeType: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export function isStudentFileCategory(value: string): value is StudentFileCategory {
  return (STUDENT_FILE_CATEGORIES as readonly string[]).includes(value);
}

export async function uploadStudentFile(file: File, category: StudentFileCategory) {
  const student = await requireVerifiedStudent("/documents");

  if (!file || file.size <= 0) {
    throw new Error("Choose a file to upload.");
  }
  if (file.size > STUDENT_STORAGE_MAX_BYTES) {
    throw new Error("The file is larger than the 50 MB storage limit.");
  }

  const safeName = sanitizeFileName(file.name || "document");
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const path = `${student.id}/${category}/${timestamp}-${crypto.randomUUID()}-${safeName}`;

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.storage.from(STUDENT_STORAGE_BUCKET).upload(path, file, {
    cacheControl: "3600",
    contentType: file.type || "application/octet-stream",
    upsert: false,
  });

  if (error) {
    console.error("student_storage_upload_failed", { category, code: error.name });
    throw new Error("We could not store that file securely. Please try again.");
  }

  return { path, name: safeName };
}

export async function listStudentFiles(): Promise<StudentStoredFile[]> {
  const student = await requireVerifiedStudent("/documents");
  const supabase = await createSupabaseServerClient();
  const files: StudentStoredFile[] = [];

  for (const category of STUDENT_FILE_CATEGORIES) {
    const { data, error } = await supabase.storage
      .from(STUDENT_STORAGE_BUCKET)
      .list(`${student.id}/${category}`, {
        limit: 100,
        sortBy: { column: "created_at", order: "desc" },
      });

    if (error) {
      console.error("student_storage_list_failed", { category, code: error.name });
      continue;
    }

    for (const item of data ?? []) {
      if (!item.id) continue;
      files.push({
        category,
        name: item.name,
        path: `${student.id}/${category}/${item.name}`,
        size: typeof item.metadata?.size === "number" ? item.metadata.size : null,
        mimeType: typeof item.metadata?.mimetype === "string" ? item.metadata.mimetype : null,
        createdAt: item.created_at ?? null,
        updatedAt: item.updated_at ?? null,
      });
    }
  }

  return files.sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
}

export async function createStudentFileSignedUrl(path: string, expiresInSeconds = 120) {
  const student = await requireVerifiedStudent("/documents");
  const prefix = `${student.id}/`;

  if (!path.startsWith(prefix) || path.includes("..")) {
    throw new Error("That file path is not available to this student.");
  }

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.storage
    .from(STUDENT_STORAGE_BUCKET)
    .createSignedUrl(path, expiresInSeconds, { download: true });

  if (error || !data?.signedUrl) {
    console.error("student_storage_signed_url_failed", { code: error?.name ?? "missing_url" });
    throw new Error("We could not prepare that file for download.");
  }

  return data.signedUrl;
}

function sanitizeFileName(name: string) {
  const cleaned = name
    .normalize("NFKC")
    .replace(/[\\/\0\r\n\t]+/g, "-")
    .replace(/[^A-Za-z0-9._() -]/g, "-")
    .replace(/\s+/g, " ")
    .replace(/-+/g, "-")
    .trim();

  return (cleaned || "document").slice(-180);
}
