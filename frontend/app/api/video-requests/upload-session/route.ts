import { NextRequest, NextResponse } from "next/server";
import { getStudentIdentity } from "@/lib/auth";
import { getStudentVideoRequest } from "@/lib/student-api";
import { requireSupabaseConfig } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const BUCKET = "Amaris Mathematics Academy";
const ONE_GIB = 1024 * 1024 * 1024;
const EXTENSIONS: Record<string, string> = {
  "application/pdf": ".pdf",
  "image/jpeg": ".jpg",
  "image/png": ".png",
};
const PRIVATE_HEADERS = { "Cache-Control": "private, no-store" };

export async function POST(request: NextRequest) {
  const student = await getStudentIdentity();
  if (!student || !student.emailVerified) {
    return NextResponse.json({ detail: "Log in with a verified student account." }, {
      status: student ? 403 : 401, headers: PRIVATE_HEADERS,
    });
  }
  const origin = request.headers.get("origin");
  const siteUrl = request.nextUrl.origin;
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const expected = new URL(siteUrl);
  if (forwardedProto === "https" || forwardedProto === "http") expected.protocol = forwardedProto + ":";
  if (origin && origin !== expected.origin) {
    return NextResponse.json({ detail: "Cross-site uploads are forbidden." }, { status: 403, headers: PRIVATE_HEADERS });
  }
  try {
    const payload = await request.json() as {
      request_reference?: string; content_type?: string; size_bytes?: number;
    };
    const reference = payload.request_reference;
    const fileSize = payload.size_bytes;
    const extension = EXTENSIONS[payload.content_type ?? ""];
    if (!reference || !/^VRQ-[A-Za-z0-9_-]{8,64}$/.test(reference)
      || !extension || !Number.isSafeInteger(fileSize)
      || !fileSize || fileSize < 1 || fileSize > ONE_GIB) {
      return NextResponse.json({ detail: "Choose a PDF, JPEG or PNG document no larger than 1 GB." }, {
        status: 400, headers: PRIVATE_HEADERS,
      });
    }
    const videoRequest = await getStudentVideoRequest(reference);
    const prefix = videoRequest.document_upload_prefix;
    if (videoRequest.status !== "pending_payment"
      || !prefix?.startsWith(student.id + "/video-requests/")
      || !new RegExp("^" + student.id + "/video-requests/[a-f0-9-]{36}/documents/$").test(prefix)
      || !videoRequest.upload_expires_at
      || new Date(videoRequest.upload_expires_at).getTime() <= Date.now()
      || videoRequest.document_count >= 5
      || videoRequest.document_total_bytes + fileSize > ONE_GIB) {
      return NextResponse.json({ detail: "Upload unavailable or document quota reached." }, {
        status: 409, headers: PRIVATE_HEADERS,
      });
    }
    const path = prefix + crypto.randomUUID() + extension;
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase.storage.from(BUCKET).createSignedUploadUrl(path);
    if (error || !data?.token) {
      return NextResponse.json({ detail: "Private storage upload authorization failed." }, {
        status: 503, headers: PRIVATE_HEADERS,
      });
    }
    const projectUrl = new URL(requireSupabaseConfig().url);
    if (projectUrl.protocol !== "https:" || !/^[a-z0-9-]+\.supabase\.co$/.test(projectUrl.hostname)) {
      throw new Error("Supabase storage endpoint is invalid.");
    }
    const storageHost = projectUrl.hostname.replace(/\.supabase\.co$/, ".storage.supabase.co");
    return NextResponse.json({
      storage_endpoint: "https://" + storageHost + "/storage/v1/upload/resumable",
      token: data.token, path, bucket: BUCKET,
    }, { headers: PRIVATE_HEADERS });
  } catch {
    return NextResponse.json({ detail: "Could not authorize this document upload." }, {
      status: 503, headers: PRIVATE_HEADERS,
    });
  }
}
