import type { Metadata } from "next";
import Link from "next/link";
import { Bell, ArrowRight } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { StudentDashboardNavigation } from "@/components/dashboard/student-navigation";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentOrders, type StudentOrder } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Account Updates", robots: { index: false, follow: false } };

function detailHref(order: StudentOrder): string {
  const reference = encodeURIComponent(order.reference);
  if (order.kind === "live_class") return `/book-online-live-class/confirmation?reference=${reference}`;
  if (order.kind === "video_request") return `/request-a-video/confirmation?reference=${reference}`;
  return "/dashboard/orders";
}

export default async function StudentNotificationsPage() {
  await requireVerifiedStudent("/dashboard/notifications");
  let updates: StudentOrder[] = [];
  let available = true;
  try {
    const result = await getStudentOrders();
    updates = result.orders.slice(0, 30);
  } catch {
    available = false;
  }

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto grid max-w-7xl gap-7 px-5 py-12 lg:grid-cols-[240px_1fr] lg:px-8">
        <StudentDashboardNavigation currentPath="/dashboard/notifications" />
        <div className="min-w-0">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-4xl font-semibold">Account updates</h1>
          <p className="mt-3 text-[#60708a]">Latest payment, booking and video-request status from your account. These are live status updates, not read/unread email notifications.</p>
          {!available ? (
            <div role="status" className="mt-7 rounded-2xl border border-amber-300 bg-amber-50 p-6">
              Updates cannot be loaded at the moment. Please try again shortly.
            </div>
          ) : updates.length ? (
            <ul className="mt-7 grid gap-4">
              {updates.map((item) => (
                <li key={`${item.kind}:${item.reference}`} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[#60708a]">{item.kind.replaceAll("_", " ")}</p>
                  <h2 className="mt-2 text-lg font-semibold">{item.title}</h2>
                  <p className="mt-2 text-sm text-[#60708a]">Current status: {item.status_label}</p>
                  <Link href={detailHref(item)} className="mt-3 inline-flex min-h-11 items-center gap-2 font-semibold text-[#1f5bbd]">View details <ArrowRight className="size-4" aria-hidden="true" /></Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-7 rounded-2xl border border-[#dce4ef] bg-white p-7">
              <Bell className="size-8 text-[#1f5bbd]" aria-hidden="true" />
              <h2 className="mt-4 text-2xl font-semibold">Nothing new to show</h2>
              <p className="mt-3 text-[#60708a]">Your account activity updates will appear here after an order or request.</p>
            </div>
          )}
        </div>
      </section>
      <Footer />
    </main>
  );
}
