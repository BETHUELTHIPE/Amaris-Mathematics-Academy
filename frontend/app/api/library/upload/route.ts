import { NextResponse } from "next/server";
import { libraryRequest, libraryToken, LibraryError } from "@/lib/library-api";
import { boundedBody, libraryFailure, privateLibraryHeaders } from "@/lib/library-http";

export const dynamic = "force-dynamic";
export async function POST(request: Request): Promise<Response> {
  try {
    if (request.headers.get("origin") !== new URL(request.url).origin) throw new LibraryError(403, "Submit documents from the Amaris website.");
    const token = await libraryToken();
    // Check the Django-approved tutor role before buffering a large request.
    const approved = await libraryRequest("tutor", "", {}, token);
    if (!approved.ok) throw new LibraryError(approved.status, "Only approved tutors can upload Library documents.");
    const type = request.headers.get("content-type") || "";
    if (!type.startsWith("multipart/form-data;")) throw new LibraryError(400, "Choose a document using the upload form.");
    const body = await boundedBody(request, 51 * 1024 * 1024);
    const form = await new Response(body, { headers: { "Content-Type": type } }).formData();
    const file = form.get("file");
    if (!(file instanceof File) || file.size > 50 * 1024 * 1024 || file.size === 0) throw new LibraryError(400, "Choose a non-empty document up to 50 MB.");
    const response = await libraryRequest("tutor", "", { method: "POST", body: form }, token);
    const result: unknown = await response.json().catch(() => ({ detail: "The upload could not be confirmed. Refresh before trying again." }));
    return NextResponse.json(result, { status: response.status, headers: privateLibraryHeaders });
  } catch (error) { return libraryFailure(error); }
}
