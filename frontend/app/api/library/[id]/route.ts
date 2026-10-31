import { NextResponse } from "next/server";
import { libraryRequest, LibraryError } from "@/lib/library-api";
import { boundedBody, libraryFailure, privateLibraryHeaders, validLibraryId } from "@/lib/library-http";
export const dynamic = "force-dynamic";
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  try {
    if (request.headers.get("origin") !== new URL(request.url).origin) throw new LibraryError(403, "Use the Amaris website to update documents.");
    const { id } = await params;
    if (!validLibraryId(id)) throw new LibraryError(400, "Invalid document.");
    const input = JSON.parse(await (await boundedBody(request, 1024)).text()) as { is_published?: unknown };
    if (typeof input.is_published !== "boolean") throw new LibraryError(400, "Choose the publication status.");
    const response = await libraryRequest("tutor", `${id}/`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_published: input.is_published }),
    });
    return NextResponse.json(await response.json(), { status: response.status, headers: privateLibraryHeaders });
  } catch (error) { return libraryFailure(error); }
}
