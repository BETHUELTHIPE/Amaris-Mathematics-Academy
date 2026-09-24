import { NextResponse, type NextRequest } from "next/server";
import { requireVerifiedStudent } from "@/lib/auth";
import { createStudentCustomVideoRequest } from "@/lib/student-api";

export async function POST(request: NextRequest) {
  await requireVerifiedStudent("/request-your-own-video");

  const formData = await request.formData();
  if (!formData.get("idempotency_key")) {
    formData.set("idempotency_key", `video-${crypto.randomUUID().replaceAll("-", "")}`);
  }

  try {
    const created = await createStudentCustomVideoRequest(formData);
    const destination = new URL("/request-your-own-video/checkout", request.url);
    destination.searchParams.set("reference", created.request_reference);
    return NextResponse.redirect(destination, 303);
  } catch {
    const destination = new URL("/request-your-own-video", request.url);
    destination.searchParams.set("error", "request");
    return NextResponse.redirect(destination, 303);
  }
}
