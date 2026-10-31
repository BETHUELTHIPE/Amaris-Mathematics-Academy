import { NextResponse } from "next/server";
import { LibraryError } from "@/lib/library-api";

export const privateLibraryHeaders = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
export const validLibraryId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export function libraryFailure(error: unknown): Response {
  return NextResponse.json({ detail: error instanceof LibraryError ? error.message : "The Library is temporarily unavailable." }, {
    status: error instanceof LibraryError ? error.status : 503, headers: privateLibraryHeaders,
  });
}
export async function boundedBody(request: Request, maximum: number): Promise<Blob> {
  if (Number(request.headers.get("content-length")) > maximum) throw new LibraryError(413, "The uploaded document is too large.");
  const reader = request.body?.getReader();
  if (!reader) throw new LibraryError(400, "Choose a document to upload.");
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let length = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > maximum) {
      await reader.cancel();
      throw new LibraryError(413, "The uploaded document is too large.");
    }
    chunks.push(new Uint8Array(value));
  }
  return new Blob(chunks);
}
