import { NextResponse } from "next/server";
import { libraryRequest, LibraryError } from "@/lib/library-api";
import { libraryFailure, privateLibraryHeaders, validLibraryId } from "@/lib/library-http";
export const dynamic = "force-dynamic";
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  try {
    const { id } = await params;
    if (!validLibraryId(id)) throw new LibraryError(400, "Invalid document.");
    const role = new URL(request.url).searchParams.get("role") === "tutor" ? "tutor" : "student";
    const response = await libraryRequest(role, `${id}/download/`);
    if (response.status === 302) {
      const location = response.headers.get("location");
      if (!location || new URL(location).protocol !== "https:") throw new LibraryError(503, "The download could not be prepared.");
      return new NextResponse(null, { status: 302, headers: { ...privateLibraryHeaders, Location: location, "Referrer-Policy": "no-referrer" } });
    }
    if (!response.ok) throw new LibraryError(response.status, response.status === 404 ? "This document is no longer available." : "The download is temporarily unavailable.");
    return new NextResponse(response.body, { headers: {
      ...privateLibraryHeaders,
      "Content-Type": response.headers.get("content-type") || "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") || "attachment",
    } });
  } catch (error) { return libraryFailure(error); }
}
