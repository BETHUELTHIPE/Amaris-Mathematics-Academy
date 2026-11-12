export const MAX_TUTOR_VIDEO_BYTES = 50 * 1024 * 1024;

export function tutorVideoRequestError(request) {
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin || request.headers.get("sec-fetch-site") === "cross-site") {
    return { status: 403, detail: "Open the tutor dashboard and submit your video from there." };
  }
  const type = request.headers.get("content-type") || "";
  if (!/^multipart\/form-data\s*;.*boundary=/i.test(type)) {
    return { status: 415, detail: "Submit one video using the upload form." };
  }
  const length = request.headers.get("content-length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_TUTOR_VIDEO_BYTES + 65536)) {
    return { status: 413, detail: "The video exceeds the upload size limit." };
  }
  return null;
}
