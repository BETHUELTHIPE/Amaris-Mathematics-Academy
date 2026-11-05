import { applicationRequest, ApplicationError } from "@/lib/tutor-applications";

export const dynamic = "force-dynamic";
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await params;
  const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox" };
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Document not found.", { status: 404, headers });
  try {
    const response = await applicationRequest(`documents/${id}/`);
    if (!response.ok) return new Response("Document unavailable.", { status: response.status, headers });
    return new Response(response.body, { headers: { ...headers, "Content-Type": "application/octet-stream", "Content-Disposition": response.headers.get("content-disposition") || "attachment" } });
  } catch (error) {
    return new Response(error instanceof ApplicationError ? error.message : "Document unavailable.", { status: error instanceof ApplicationError ? error.status : 503, headers });
  }
}
