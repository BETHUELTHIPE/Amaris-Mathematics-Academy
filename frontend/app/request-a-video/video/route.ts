import { requireVerifiedStudent } from "@/lib/auth";
import { streamStudentRequestedVideo } from "@/lib/student-api";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const reference = new URL(request.url).searchParams.get("reference")?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(reference)) {
    return new Response("Invalid video request reference.", { status: 400 });
  }
  await requireVerifiedStudent(`/request-a-video/confirmation?reference=${encodeURIComponent(reference)}`);
  try {
    const video = await streamStudentRequestedVideo(reference);
    if (!video.ok) return new Response("Video unavailable.", { status: 404 });
    return new Response(video.body, {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": "inline",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("Video unavailable.", {
      status: 503,
      headers: { "Cache-Control": "private, no-store" },
    });
  }
}

