import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CreditCard } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { StudentDashboardNavigation } from "@/components/dashboard/student-navigation";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentOrders, type StudentOrder } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Orders & Payments", robots: { index: false, follow: false } };

function orderLink(order: StudentOrder): string {
  const reference = encodeURIComponent(order.reference);
  if (order.kind === "video_request") return `/request-a-video/confirmation?reference=${reference}`;
  if (order.kind === "live_class") return `/book-online-live-class/confirmation?reference=${reference}`;
  return "/dashboard/courses";
}

export default async function StudentOrdersPage() {
  await requireVerifiedStudent("/dashboard/orders");
  let orders: StudentOrder[] = [];
  let available = true;
  try {
    ({ orders } = await getStudentOrders());
  } catch {
    available = false;
  }

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto grid max-w-7xl gap-7 px-5 py-12 lg:grid-cols-[240px_1fr] lg:px-8">
        <StudentDashboardNavigation currentPath="/dashboard/orders" />
        <div className="min-w-0">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-4xl font-semibold">Orders & payments</h1>
          <p className="mt-3 text-[#60708a]">Verified server-side status for your course purchases, live classes and requested videos. A pending payment never grants course or Zoom access.</p>
          {!available ? (
            <div role="status" className="mt-7 rounded-2xl border border-amber-300 bg-amber-50 p-6">
              Your payment history is temporarily unavailable. Please retry later rather than making a duplicate payment.
            </div>
          ) : orders.length ? (
            <ul className="mt-7 grid gap-4">
              {orders.map((order) => (
                <li key={`${order.kind}:${order.reference}`} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wide text-[#60708a]">{order.kind.replaceAll("_", " ")}</p>
                      <h2 className="mt-2 text-xl font-semibold">{order.title}</h2>
                      <p className="mt-2 break-all font-mono text-xs text-[#60708a]">{order.reference}</p>
                    </div>
                    <span className="rounded-full bg-[#edf3ff] px-3 py-1.5 text-sm font-semibold text-[#0b2a5b]">{order.status_label}</span>
                  </div>
                  <p className="mt-4 text-sm text-[#60708a]">
                    {new Intl.NumberFormat("en-ZA", { style: "currency", currency: order.currency }).format(Number(order.amount))}
                    {" · "}
                    {new Date(order.created_at).toLocaleDateString("en-ZA", { dateStyle: "medium" })}
                  </p>
                  <Link href={orderLink(order)} className="mt-4 inline-flex min-h-11 items-center gap-2 font-semibold text-[#1f5bbd]">
                    {order.kind === "course" ? "View my courses" : "View status and documents"} <ArrowRight className="size-4" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-7 rounded-2xl border border-[#dce4ef] bg-white p-7">
              <CreditCard className="size-8 text-[#1f5bbd]" aria-hidden="true" />
              <h2 className="mt-4 text-2xl font-semibold">No orders yet</h2>
              <p className="mt-3 text-[#60708a]">Your purchases and payment statuses will appear here.</p>
              <Link href="/courses" className="mt-5 inline-flex min-h-11 items-center gap-2 font-bold text-[#1f5bbd]">Explore courses <ArrowRight className="size-4" /></Link>
            </div>
          )}
        </div>
      </section>
      <Footer />
    </main>
  );
}
