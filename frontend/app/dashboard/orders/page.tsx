import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { ArrowRight, Download, ReceiptText, ShoppingBag } from "lucide-react";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentOrders, type StudentOrder } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Orders & Payments",
  robots: { index: false, follow: false },
};

const successfulStatuses = new Set(["paid", "confirmed", "completed", "ready"]);
const attentionStatuses = new Set(["failed", "cancelled", "expired", "payment_review"]);

function OrdersSkeleton() {
  return <div role="status" aria-label="Loading your private orders" className="space-y-4">
    <div aria-hidden="true" className="grid gap-4 sm:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => <div key={i} className="h-28 rounded-2xl border border-[#dce4ef] bg-white p-5"><div className="h-4 w-24 rounded bg-[#e9eef6]" /><div className="mt-4 h-8 w-16 rounded bg-[#e9eef6]" /></div>)}
    </div>
    <div aria-hidden="true" className="min-h-48 rounded-3xl border border-[#dce4ef] bg-white p-6">
      <div className="h-6 w-44 rounded bg-[#e9eef6]" /><div className="mt-6 h-24 rounded-xl bg-[#f1f5fa]" />
    </div>
    <span className="sr-only">Loading private orders records</span>
  </div>;
}

async function OrdersContent() {
  let orders: StudentOrder[] = [];
  let serviceAvailable = true;
  try {
    orders = await getStudentOrders();
  } catch {
    serviceAvailable = false;
  }

  const paidOrders = orders.filter((order) => Boolean(order.paid_at)).length;
  const awaitingPayment = orders.filter((order) =>
    ["pending", "pending_payment"].includes(order.status),
  ).length;


  return <>
   <div className="grid gap-4 sm:grid-cols-3">
      {[
        ["All orders", orders.length],
        ["Payments received", paidOrders],
        ["Awaiting payment", awaitingPayment],
      ].map(([label, value]) => <div key={label} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-5 sm:p-6">
        <p className="text-sm text-[#60708a]">{label}</p>
        <p className="mt-3 text-3xl font-bold tracking-tight">{serviceAvailable ? value : "—"}</p>
      </div>)}
    </div>

    {!serviceAvailable && <div role="alert" className="mt-6 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm leading-6 text-[#765314]">
      Your orders are temporarily unavailable. No payment action is required; try again shortly.
    </div>}

    {serviceAvailable && orders.length === 0 && <section className="mt-6 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-9">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><ShoppingBag aria-hidden="true" className="size-6" /></div>
      <h2 className="mt-5 text-2xl font-semibold">No orders yet.</h2>
      <p className="mt-2 max-w-xl text-sm leading-7 text-[#60708a]">Your verified course purchases, live-class bookings and requested videos will appear here.</p>
      <Link href="/courses" className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white sm:w-fit">Browse courses <ArrowRight aria-hidden="true" className="size-4" /></Link>
    </section>}

    {orders.length > 0 && <section className="mt-6 min-w-0 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8">
      <div className="flex items-center gap-3">
        <ReceiptText aria-hidden="true" className="size-5 text-[#1f5bbd]" />
        <h2 className="text-xl font-semibold">Order history</h2>
      </div>
      <div className="mt-5 grid gap-4">
        {orders.map((order) => {
          const invoiceHref = invoiceLink(order);
          return <article key={`${order.kind}-${order.reference}`} className="min-w-0 rounded-2xl border border-[#dce4ef] p-4 sm:p-5">
            <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{kindLabel(order.kind)}</span>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusClass(order.status)}`}>{order.status_label}</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold [overflow-wrap:anywhere]">{order.title}</h3>
                <p className="mt-1 text-sm leading-6 text-[#60708a]">{order.detail}</p>
                <p className="mt-2 break-all font-mono text-xs text-[#60708a]">{order.reference}</p>
              </div>
              <div className="shrink-0 sm:text-right">
                <p className="text-xl font-bold">{formatMoney(order.amount, order.currency)}</p>
                <time dateTime={order.created_at} className="mt-1 block text-xs text-[#60708a]">{formatDate(order.created_at)}</time>
              </div>
            </div>
            <div className="mt-4 flex flex-col gap-2 border-t border-[#e7edf5] pt-4 sm:flex-row sm:flex-wrap">
              <Link href={order.href} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full border border-[#bfd0e8] px-4 text-sm font-bold text-[#194f95] sm:w-fit">View details <ArrowRight aria-hidden="true" className="size-4" /></Link>
              {invoiceHref && <Link href={invoiceHref} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-4 text-sm font-bold text-white sm:w-fit">Download invoice <Download aria-hidden="true" className="size-4" /></Link>}
              {order.invoice_number && <span className="flex min-h-11 min-w-0 items-center text-xs text-[#60708a] sm:ml-auto">Invoice <span className="ml-1 break-all font-mono">{order.invoice_number}</span></span>}
            </div>
          </article>;
        })}
      </div>
    </section>}
  </>;
}

export default async function OrdersPage() {
  await requireVerifiedStudent("/dashboard/orders");
  return <StudentDashboardShell
    active="orders"
    title="Orders & payments"
    description="Review your 100 most recent course, live class and requested video orders in one private account view."
  >
    <Suspense fallback={<OrdersSkeleton />}>
      <OrdersContent />
    </Suspense>
  </StudentDashboardShell>;
}


function kindLabel(kind: StudentOrder["kind"]): string {
  if (kind === "live_class") return "Live class";
  if (kind === "video_request") return "Requested video";
  return "Course";
}

function statusClass(status: string): string {
  if (successfulStatuses.has(status)) return "bg-[#daf5ec] text-[#13715f]";
  if (attentionStatuses.has(status)) return "bg-[#ffe7e7] text-[#a52828]";
  return "bg-[#fff3d6] text-[#7b5710]";
}

function invoiceLink(order: StudentOrder): string | null {
  if (!order.invoice_ready) return null;
  const reference = encodeURIComponent(order.reference);
  if (order.kind === "course") return `/dashboard/orders/invoice?reference=${reference}`;
  if (order.kind === "live_class") return `/book-online-live-class/invoice?reference=${reference}`;
  return `/request-a-video/invoice?reference=${reference}`;
}

function formatMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return `${currency} ${amount}`;
  try {
    return new Intl.NumberFormat("en-ZA", { style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg" }).format(date);
}
