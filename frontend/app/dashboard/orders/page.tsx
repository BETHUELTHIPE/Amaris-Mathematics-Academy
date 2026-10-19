import type { Metadata } from "next";
import Link from "next/link";
import { Download, ReceiptText } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentOrders, type StudentOrder } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Student Orders and Invoices",
  robots: { index: false, follow: false },
};

function invoiceLink(order: StudentOrder): string | null {
  if (!order.invoice_ready || !order.invoice_number) return null;
  const reference = encodeURIComponent(order.reference);
  if (order.kind === "course") return `/dashboard/orders/invoice?reference=${reference}`;
  if (order.kind === "live_class") return `/book-online-live-class/invoice?reference=${reference}`;
  return null;
}

export default async function StagingStudentOrdersPage() {
  await requireVerifiedStudent("/dashboard/orders");
  let orders: StudentOrder[] = [];
  let available = true;
  try {
    orders = await getStudentOrders();
  } catch {
    available = false;
  }
  return <main className="min-h-screen bg-[#f5f7fb]">
    <Header />
    <section className="mx-auto max-w-6xl px-5 py-12 lg:px-8">
      <Link href="/dashboard" className="text-sm font-semibold text-[#1f5bbd] underline">Back to dashboard</Link>
      <p className="eyebrow mt-6">Private student account</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Orders &amp; payments</h1>
      <p className="mt-4 max-w-2xl text-[#60708a]">Only your own verified bookings and purchases are shown. Paid invoice PDFs are stored privately and never publicly shared.</p>
      {!available && <div role="alert" className="mt-8 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm text-[#765314]">
        Your orders are temporarily unavailable. No additional payment is required.
      </div>}
      {available && orders.length === 0 && <section className="mt-8 rounded-2xl border border-[#dce4ef] bg-white p-8">
        <ReceiptText className="size-7 text-[#1f5bbd]" aria-hidden="true"/>
        <h2 className="mt-4 text-xl font-semibold">No orders yet</h2>
        <p className="mt-2 text-sm text-[#60708a]">Your successful sandbox test booking will appear here after PayFast confirms payment.</p>
      </section>}
      {available && orders.length > 0 && <div className="mt-8 grid gap-4">
        {orders.map((order) => <article key={order.kind + order.reference} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-5 sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <span className="text-xs font-bold uppercase tracking-wide text-[#1f5bbd]">{order.kind.replace("_", " ")}</span>
              <h2 className="mt-2 break-words text-lg font-semibold">{order.title}</h2>
              <p className="mt-1 text-sm text-[#60708a]">{order.detail}</p>
              <p className="mt-2 break-all font-mono text-xs text-[#60708a]">{order.reference}</p>
            </div>
            <div className="text-sm">
              <p className="font-bold">{order.currency} {order.amount}</p>
              <p className="mt-1 text-[#60708a]">{order.status_label}</p>
            </div>
          </div>
          {order.invoice_number && <p className="mt-4 break-all text-xs text-[#60708a]">Invoice: {order.invoice_number}</p>}
          {invoiceLink(order) && <a className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-2 font-bold text-white" href={invoiceLink(order)!}>
            <Download className="size-4" aria-hidden="true"/> Download invoice (PDF)
          </a>}
        </article>)}
      </div>}
    </section>
    <Footer />
  </main>;
}
