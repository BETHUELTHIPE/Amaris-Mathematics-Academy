import { subscriptionRequest } from "@/lib/subscription-api";
export const dynamic = "force-dynamic";
export async function GET(_request: Request, { params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  if (!/^SUB-[A-F0-9]{32}$/.test(reference)) return new Response("Invoice not found.", { status: 404 });
  try {
    const response = await subscriptionRequest(`${reference}/invoice/`);
    return new Response(response.body, { headers: { "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="INV-${reference}.pdf"`, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } });
  } catch { return new Response("Invoice temporarily unavailable.", { status: 503, headers: { "Cache-Control": "private, no-store" } }); }
}
