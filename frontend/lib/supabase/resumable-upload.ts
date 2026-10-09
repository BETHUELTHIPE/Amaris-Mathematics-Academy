/**
 * Browser-to-Supabase TUS upload: 6 MiB chunks avoid application-server buffering.
 * A signed upload token is issued only to a verified student for a pending request.
 * The token and resumable location remain in memory; neither is logged or persisted.
 */
export type SignedStudentUpload = {
  storage_endpoint: string;
  token: string;
  path: string;
  bucket: string;
};

const CHUNK_BYTES = 6 * 1024 * 1024;
const RETRY_DELAYS = [0, 1500, 3500, 7000, 12000];

function metadataHeader(metadata: Record<string, string>): string {
  return Object.entries(metadata).map(([key, value]) => key + " " + btoa(value)).join(",");
}

async function readOffset(url: string, token: string): Promise<number> {
  const response = await fetch(url, {
    method: "HEAD",
    headers: { "Tus-Resumable": "1.0.0", "x-signature": token },
    cache: "no-store",
  });
  const offset = Number(response.headers.get("Upload-Offset"));
  if (!response.ok || !Number.isSafeInteger(offset) || offset < 0) {
    throw new Error("Resumable upload could not recover its position.");
  }
  return offset;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function uploadStudentDocument(
  file: File,
  signed: SignedStudentUpload,
  onProgress: (percent: number) => void,
): Promise<void> {
  const endpoint = new URL(signed.storage_endpoint);
  if (endpoint.protocol !== "https:" || !endpoint.hostname.endsWith(".storage.supabase.co")) {
    throw new Error("Storage endpoint is invalid.");
  }
  const init = await fetch(endpoint.toString(), {
    method: "POST",
    headers: {
      "Tus-Resumable": "1.0.0",
      "Upload-Length": String(file.size),
      "Upload-Metadata": metadataHeader({
        bucketName: signed.bucket,
        objectName: signed.path,
        contentType: file.type,
        cacheControl: "0",
      }),
      "x-signature": signed.token,
    },
    cache: "no-store",
  });
  if (init.status !== 201) {
    throw new Error("The private resumable upload could not start. Check the Supabase storage limit.");
  }
  const location = init.headers.get("Location");
  if (!location) throw new Error("Storage did not provide a resumable upload URL.");
  const uploadUrl = new URL(location, endpoint);
  if (uploadUrl.origin !== endpoint.origin) throw new Error("Unexpected storage upload location.");

  let offset = 0;
  while (offset < file.size) {
    const next = Math.min(offset + CHUNK_BYTES, file.size);
    let complete = false;
    for (const retry of RETRY_DELAYS) {
      if (retry) await delay(retry);
      try {
        const response = await fetch(uploadUrl.toString(), {
          method: "PATCH",
          headers: {
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": String(offset),
            "Content-Type": "application/offset+octet-stream",
            "x-signature": signed.token,
          },
          body: file.slice(offset, next),
          cache: "no-store",
        });
        if (response.ok) {
          const remoteOffset = Number(response.headers.get("Upload-Offset"));
          offset = Number.isSafeInteger(remoteOffset) && remoteOffset >= next ? remoteOffset : next;
          onProgress(Math.min(100, Math.round((offset / file.size) * 100)));
          complete = true;
          break;
        }
        if (![408, 409, 429, 500, 502, 503, 504].includes(response.status)) {
          throw new Error("Storage rejected the document upload.");
        }
      } catch (error) {
        if (error instanceof Error && error.message === "Storage rejected the document upload.") throw error;
      }
      try {
        const serverOffset = await readOffset(uploadUrl.toString(), signed.token);
        if (serverOffset > file.size) throw new Error("Invalid storage offset.");
        if (serverOffset >= next) {
          offset = serverOffset;
          onProgress(Math.min(100, Math.round((offset / file.size) * 100)));
          complete = true;
          break;
        }
        // Restart from the server's acknowledged position, never replay acknowledged bytes.
        if (serverOffset !== offset) {
          offset = serverOffset;
          complete = true;
          break;
        }
      } catch {
        // Retry transient network errors without exposing signed tokens.
      }
    }
    if (!complete) throw new Error("Upload interrupted. Please retry on a stable connection.");
  }
  onProgress(100);
}
