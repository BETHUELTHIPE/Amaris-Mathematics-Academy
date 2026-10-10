import { NextRequest, NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";
import { controlStudentVideoRequestUpload } from "@/lib/student-api";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ reference: string }> },
) {
  const expected = new URL(request.nextUrl.toString());
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  if (forwardedProto === "https" || forwardedProto === "http") {
    expected.protocol = `${forwardedProto}:`;
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== expected.origin) {
    return NextResponse.json({ detail: "Cross-site uploads are not allowed." }, { status: 403 });
  }
  const student = await getStudentIdentity();
  if (!student?.emailVerified) {
    return NextResponse.json(
      { detail: "Log in as a verified student to upload supporting files." },
      { status: student ? 403 : 401 },
    );
  }
  try {
    const { reference } = await params;
    const values: unknown = await request.json();
    if (!values || typeof values !== "object" || Array.isArray(values)) {
      return NextResponse.json({ detail: "Invalid upload metadata." }, { status: 400 });
    }
    const result = await controlStudentVideoRequestUpload(
      reference, values as Record<string, unknown>,
    );
    return NextResponse.json(result, { headers: { "Cache-Control": "private, no-store" } });
  } catch {
    return NextResponse.json(
      { detail: "Upload rejected or private storage is unavailable. Please try again." },
      { status: 400, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
