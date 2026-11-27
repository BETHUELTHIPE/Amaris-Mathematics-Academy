type Progress = (fraction: number) => void;

const chunkSize = 16 * 1024 * 1024;
const protocol = "1.0.0";

async function tusOffset(url: string) {
  const response = await fetch(url, { method: "HEAD", headers: { "Tus-Resumable": protocol }, cache: "no-store" });
  const header = response.headers.get("Upload-Offset");
  const offset = Number(header);
  if (!response.ok || header === null || !Number.isSafeInteger(offset) || offset < 0) {
    throw new Error("Vimeo did not confirm the upload position.");
  }
  return offset;
}

export async function sendVimeo(url: string, file: File, progress: Progress) {
  let offset = await tusOffset(url);
  let retries = 0;
  while (offset < file.size) {
    const end = Math.min(file.size, offset + chunkSize);
    try {
      const response = await fetch(url, {
        method: "PATCH",
        headers: { "Tus-Resumable": protocol, "Upload-Offset": String(offset),
          "Content-Type": "application/offset+octet-stream" },
        body: file.slice(offset, end),
      });
      if (!response.ok || Number(response.headers.get("Upload-Offset")) !== end) {
        throw new Error("Vimeo did not acknowledge the uploaded chunk.");
      }
      retries = 0;
      offset = end;
      progress(offset / file.size);
    } catch (error) {
      if (++retries > 3) throw error;
      await new Promise((resolve) => setTimeout(resolve, retries * 800));
      offset = await tusOffset(url);
    }
  }
  if (offset !== file.size) throw new Error("Vimeo reported an unexpected file size.");
}

export function sendS3(url: string, headers: Record<string, string>, file: File, progress: Progress) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) progress(event.loaded / event.total);
    };
    request.onload = () => request.status === 200
      ? resolve() : reject(new Error("AWS S3 rejected the upload. Try again."));
    request.onerror = () => reject(new Error("The connection to AWS S3 was interrupted."));
    request.send(file);
  });
}
