import { uploadTutorVideo, TutorApiError } from "@/lib/tutor-api";
import { tutorVideoRequestError } from "@/lib/tutor-video-request.mjs";

export const dynamic = "force-dynamic";

function response(body: unknown, status: number) {
  return Response.json(body, { status, headers: { "Cache-Control": "private, no-store", Vary: "Cookie" } });
}

export async function POST(request: Request) {
  const invalid = tutorVideoRequestError(request);
  if (invalid) return response({ detail: invalid.detail }, invalid.status);
  try {
    const result = await uploadTutorVideo(request);
    return response(result.data, result.status);
  } catch (error) {
    if (error instanceof TutorApiError) return response({ detail: error.message }, error.status);
    return response({ detail: "Upload temporarily unavailable. Please retry your submission." }, 503);
  }
}
