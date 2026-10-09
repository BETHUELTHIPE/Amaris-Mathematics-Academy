import { NextRequest, NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";
import { registerStudentVideoDocument } from "@/lib/student-api";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const privateHeaders = { "Cache-Control": "private, no-store" };
  const student = await getStudentIdentity();
  if (!student || !student.emailVerified) {
    return NextResponse.json({ detail: "Verified student login required." }, {
      status: student ? 403 : 401, headers: privateHeaders,
    });
  }
  const origin = request.headers.get("origin");
  const expected = new URL(request.nextUrl.toString());
  const proto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  if (proto === "https" || proto === "http") expected.protocol = proto + ":";
  if (origin && origin !== expected.origin) {
    return NextResponse.json({ detail: "Cross-site uploads are forbidden." }, {
      status: 403, headers: privateHeaders,
    });
  }
  try {
    const data = await request.json() as {
      request_reference?: string; storage_path?: string; original_name?: string;
      content_type?: string; size_bytes?: number;
    };
    if (!data.request_reference || !/^VRQ-[A-Za-z0-9_-]{8,64}$/.test(data.request_reference)
      || !data.storage_path || !data.original_name
      || typeof data.size_bytes !== "number") {
      return NextResponse.json({ detail: "Invalid document metadata." }, {
        status: 400, headers: privateHeaders,
      });
    }
    const result = await registerStudentVideoDocument(data as {
      request_reference: string; storage_path: string; original_name: string;
      content_type: string; size_bytes: number;
    });
    return NextResponse.json(result, { status: 201, headers: privateHeaders });
  } catch {
    return NextResponse.json({ detail: "The upload could not be verified in private storage." }, {
      status: 400, headers: privateHeaders,
    });
  }
}
