import { getTutorContractPDF, TutorApiError } from "@/lib/tutor-api";

export const dynamic = "force-dynamic";
export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const headers = { "Cache-Control": "private, no-store", Vary: "Cookie", "X-Content-Type-Options": "nosniff" };
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return new Response("Contract not found.", { status: 404, headers });
  try {
    const document = await getTutorContractPDF(id);
    return new Response(document, { headers: { ...headers, "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="amaris-tutor-employment-${id}.pdf"` } });
  } catch (error) {
    return Response.json({ detail: "The saved contract is unavailable. Please retry or contact the academy." }, { status: error instanceof TutorApiError ? error.status : 503, headers });
  }
}
