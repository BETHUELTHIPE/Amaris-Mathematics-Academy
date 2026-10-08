import { requireVerifiedStudent } from "@/lib/auth";
import { downloadStudentVideoRequestInvoice } from "@/lib/student-api";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const reference = new URL(request.url).searchParams.get("reference")?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(reference)) {
    return new Response("Invalid video request reference.", { status: 400 });
  }
  await requireVerifiedStudent(`/request-a-video/confirmation?reference=${encodeURIComponent(reference)}`);
  try {
    const invoice = await downloadStudentVideoRequestInvoice(reference);
    if (!invoice.ok) {
      return new Response("Invoice unavailable.", {
        status: invoice.status === 404 ? 404 : 503,
        headers: { "Cache-Control": "private, no-store" },
      });
    }
    return new Response(invoice.body, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": invoice.headers.get("Content-Disposition") ?? "attachment; filename=invoice.pdf",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("Invoice unavailable.", {
      status: 503,
      headers: { "Cache-Control": "private, no-store" },
    });
  }
}

