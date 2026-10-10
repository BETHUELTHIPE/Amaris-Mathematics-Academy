"use client";

/** Browser-to-private-S3 upload. Django/Next only handle authenticated metadata. */
export const VIDEO_UPLOAD_LIMIT_BYTES = 1024 * 1024 * 1024;
export const VIDEO_UPLOAD_MAX_FILES = 200;
const CONTENT_TYPES: Record<string, string> = {
  pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg",
  png: "image/png", webp: "image/webp", gif: "image/gif",
  txt: "text/plain", csv: "text/csv",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  zip: "application/zip", mp4: "video/mp4", webm: "video/webm",
};

type InitResult = { key: string; upload_id: string; part_bytes: number; parts: number };
type SignResult = { url: string };
type UploadedPart = { part_number: number; etag: string };

async function control<T>(reference: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(
    `/api/video-requests/uploads/${encodeURIComponent(reference)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `Secure upload failed (HTTP ${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function uploadPath(file: File): string {
  // Folder selection is browser-specific, so ordinary file selection remains available.
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

export async function uploadVideoRequestFiles(
  reference: string,
  files: File[],
  onProgress: (percent: number) => void,
): Promise<void> {
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (files.length > VIDEO_UPLOAD_MAX_FILES || total > VIDEO_UPLOAD_LIMIT_BYTES) {
    throw new Error("Select at most 200 files totalling no more than 1 GiB.");
  }
  if (files.some((file) => file.size <= 0)) {
    throw new Error("Empty files cannot be uploaded.");
  }
  let uploaded = 0;
  for (const file of files) {
    const name = uploadPath(file);
    const extension = name.split(".").pop()?.toLowerCase() || "";
    const content_type = CONTENT_TYPES[extension];
    if (!content_type) {
      throw new Error(`Unsupported file type: ${name}`);
    }
    const metadata = { name, size: file.size, content_type };
    const { key, upload_id, part_bytes, parts } = await control<InitResult>(
      reference, { action: "init", ...metadata },
    );
    try {
      const completed: UploadedPart[] = [];
      for (let part_number = 1; part_number <= parts; part_number += 1) {
        const start = (part_number - 1) * part_bytes;
        const end = Math.min(start + part_bytes, file.size);
        let etag = "";
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            const signed = await control<SignResult>(
              reference, { action: "part", key, upload_id, part_number },
            );
            const response = await fetch(signed.url, {
              method: "PUT",
              body: file.slice(start, end),
            });
            if (!response.ok) throw new Error(`Chunk upload failed (HTTP ${response.status}).`);
            etag = response.headers.get("ETag") || "";
            if (!etag) {
              throw new Error("Storage must expose the ETag response header in bucket CORS settings.");
            }
            break;
          } catch (error) {
            if (attempt === 2) throw error;
          }
        }
        completed.push({ part_number, etag });
        uploaded += end - start;
        onProgress(Math.min(99, Math.round((uploaded / total) * 100)));
      }
      await control(reference, {
        action: "complete", ...metadata, key, upload_id, parts: completed,
      });
    } catch (error) {
      await control(reference, { action: "abort", key, upload_id }).catch(() => undefined);
      throw error;
    }
  }
  onProgress(100);
}
