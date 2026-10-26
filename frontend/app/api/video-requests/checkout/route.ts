import { resolveCurriculumFields } from "@/lib/school-curriculum.mjs";
import { NextRequest, NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";
import { createStudentVideoRequestCheckout } from "@/lib/student-api";

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
  try {
    const student = await getStudentIdentity();
    if (!student || !student.emailVerified) {
      return NextResponse.json(
        { detail: "Log in with a verified student account to request a video." },
        { status: student ? 403 : 401, headers: { "Cache-Control": "private, no-store" } },
      );
    }
    const formData = await request.formData();
    // Reject blank mandatory fields even when HTML validation is bypassed.
    for (const [field, label] of [["request_type", "video package"], ["preferred_duration_minutes", "duration"], ["explanation_style", "explanation style"], ["instructions", "instructions"]] as const) {
      if (!String(formData.get(field) ?? "").trim()) {
        return NextResponse.json({ detail: `Enter the required ${label}.` }, { status: 400, headers: { "Cache-Control": "private, no-store" } });
      }
    }
    const attachments = formData.getAll("documents").filter(item => item instanceof File && item.size > 0);
    if (!attachments.length) {
      return NextResponse.json({ detail: "Attach at least one supporting document." }, { status: 400, headers: { "Cache-Control": "private, no-store" } });
    }
    const selection = resolveCurriculumFields(formData);
    formData.set("level", selection.level);
    formData.set("topic", selection.topic);
    const checkout = await createStudentVideoRequestCheckout(formData);
    return NextResponse.json(checkout, {
      status: 201,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Video request failed.";
    const status = /session|log in|verified/i.test(message) ? 401 : 400;
    return NextResponse.json(
      { detail: status === 401 ? "Your student session has expired. Please log in again." : "We could not create the video request. Check the form and files, then try again." },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}

