import { NextResponse, type NextRequest } from "next/server";
import { downloadStudentCourseInvoice } from "@/lib/student-api";
import { requireVerifiedStudent } from "@/lib/auth";

export const dynamic = "force-dynamic";
const privateHeaders = { "Cache-Control": "private, no-store" };

export async function GET(request: NextRequest) {
  const reference = request.nextUrl.searchParams.get("reference")?.trim();
  if (!reference || !/^[A-Za-z0-9_-]{1,100}$/.test(reference)) {
    return NextResponse.json({ detail: "A valid payment reference is required." }, { status: 400, headers: privateHeaders });
  }
  await requireVerifiedStudent("/dashboard/orders");

  try {
    const invoice = await downloadStudentCourseInvoice(reference);
    if (!invoice.ok) {
      return NextResponse.json(
        { detail: invoice.status === 404 ? "Invoice not found." : "Invoice is temporarily unavailable." },
        { status: invoice.status === 404 ? 404 : 503, headers: privateHeaders },
      );
    }
    return new NextResponse(invoice.body, {
      status: 200,
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Type": "application/pdf",
        "Content-Disposition": invoice.headers.get("Content-Disposition") ?? "attachment; filename=invoice.pdf",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Invoice is temporarily unavailable." }, { status: 503, headers: privateHeaders });
  }
}
