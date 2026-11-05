import { NextRequest, NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";
import { createStudentVideoRequestCheckout } from "@/lib/student-api";
import { boundedVideoUpload, MAX_VIDEO_UPLOAD_BODY_BYTES } from "@/lib/video-document-limits.mjs";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  const expectedOrigin = new URL(request.nextUrl.toString());
  // Render terminates HTTPS before forwarding the request to the Node server.
  const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  if (forwardedProtocol === "https" || forwardedProtocol === "http") {
    expectedOrigin.protocol = `${forwardedProtocol}:`;
  }
  if (origin && origin !== expectedOrigin.origin) {
    return NextResponse.json(
      { detail: "Cross-site video requests are not allowed." },
      { status: 403, headers: { "Cache-Control": "private, no-store" } },
    );
  }
  let upload: ReturnType<typeof boundedVideoUpload> | undefined;
  try {
    const student = await getStudentIdentity();
    if (!student || !student.emailVerified) {
      return NextResponse.json(
        { detail: "Log in with a verified student account to request a video." },
        { status: student ? 403 : 401, headers: { "Cache-Control": "private, no-store" } },
      );
    }
    const contentType = request.headers.get("content-type") ?? "";
    if (!contentType.startsWith("multipart/form-data;") || !request.body) {
      return NextResponse.json({ detail: "Submit the video request form with your documents." }, {
        status: 400, headers: { "Cache-Control": "private, no-store" },
      });
    }
    if (Number(request.headers.get("content-length")) > MAX_VIDEO_UPLOAD_BODY_BYTES) {
      return NextResponse.json({ detail: "Supporting documents must total no more than 1 GB." }, {
        status: 413, headers: { "Cache-Control": "private, no-store" },
      });
    }
    // The browser resolves curriculum fields; Django validates the submitted
    // values. Pass the multipart boundary unchanged and stream file bytes.
    upload = boundedVideoUpload(request.body);
    const checkout = await createStudentVideoRequestCheckout(upload.body, contentType, request.signal);
    return NextResponse.json(checkout, {
      status: 201,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (error) {
    if (upload?.exceeded) {
      return NextResponse.json({ detail: "Supporting documents must total no more than 1 GB." }, {
        status: 413, headers: { "Cache-Control": "private, no-store" },
      });
    }
    const message = error instanceof Error ? error.message : "Video request failed.";
    const status = /session|log in|verified/i.test(message) ? 401 : 400;
    return NextResponse.json(
      { detail: status === 401 ? "Your student session has expired. Please log in again." : "We could not create the video request. Check the form and files, then try again." },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}

