import { NextResponse } from "next/server";
import { TutorApiError, tutorFetch } from "@/lib/tutor-api";

export const dynamic = "force-dynamic";
const privateHeaders = { "Cache-Control": "private, no-store" };
const maxBody = 4096;

export async function POST(request: Request) {
  const result = (body: unknown, status: number) => NextResponse.json(body, { status, headers: privateHeaders });
  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return result({ detail: "Submit the upload from the Amaris tutor dashboard." }, 403);
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return result({ detail: "Use the tutor video upload form." }, 415);
  }
  try {
    if (Number(request.headers.get("content-length")) > maxBody) {
      return result({ detail: "Upload details are too large." }, 413);
    }
    const reader = request.body?.getReader();
    if (!reader) return result({ detail: "Upload details are missing." }, 400);
    const decoder = new TextDecoder();
    let raw = "";
    let bytes = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBody) {
        await reader.cancel();
        return result({ detail: "Upload details are too large." }, 413);
      }
      raw += decoder.decode(value, { stream: true });
    }
    const body = JSON.parse(raw + decoder.decode()) as Record<string, unknown> | null;
    const action = body?.action;
    if (!body || (action !== "start" && action !== "finish")) {
      return result({ detail: "Choose a valid upload action." }, 400);
    }
    const payload = action === "start" ? {
      provider: body.provider, filename: body.filename, size: body.size, title: body.title,
    } : { provider: body.provider, submission: body.submission, ticket: body.ticket };
    return result(await tutorFetch(`/tutor/videos/${action}/`, "POST", payload), action === "start" ? 201 : 200);
  } catch (error) {
    if (error instanceof TutorApiError) {
      return result({ detail: error.status === 429 ? "Too many upload attempts. Please wait and try again." : error.message }, error.status);
    }
    return result({ detail: "The upload details could not be read." }, 400);
  }
}
