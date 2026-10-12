import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BellRing } from "lucide-react";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentNotifications, type StudentNotification } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Notifications",
  robots: { index: false, follow: false },
};

export default async function NotificationsPage() {
  await requireVerifiedStudent("/dashboard/notifications");
  let notifications: StudentNotification[] = [];
  let serviceAvailable = true;
  try {
    notifications = await getStudentNotifications();
  } catch {
    serviceAvailable = false;
  }

  return <StudentDashboardShell
    active="notifications"
    title="Notifications"
    description="Payment confirmations, live-class reminders and requested-video updates appear here."
  >
    {!serviceAvailable && <div role="alert" className="rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm leading-6 text-[#765314]">
      Notifications are temporarily unavailable. Your account and purchases remain secure; try again shortly.
    </div>}

    {serviceAvailable && notifications.length === 0 && <section className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-9">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><BellRing aria-hidden="true" className="size-6" /></div>
      <h2 className="mt-5 text-2xl font-semibold">You’re all caught up.</h2>
      <p className="mt-2 max-w-xl text-sm leading-7 text-[#60708a]">New payment, booking and requested-video updates will be listed here as they happen.</p>
      <Link href="/dashboard" className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white sm:w-fit">Back to overview <ArrowRight aria-hidden="true" className="size-4" /></Link>
    </section>}

    {notifications.length > 0 && <section className="min-w-0 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8">
      <h2 className="text-xl font-semibold">Recent updates</h2>
      <div className="mt-5 grid gap-3">
        {notifications.map((notification) => <article key={notification.id} className="min-w-0 rounded-2xl border border-[#dce4ef] p-4 sm:p-5">
          <div className="flex min-w-0 gap-3 sm:gap-4">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#edf3ff] text-[#1f5bbd]"><BellRing aria-hidden="true" className="size-5" /></div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                <h3 className="font-semibold [overflow-wrap:anywhere]">{notification.title}</h3>
                <time dateTime={notification.occurred_at} className="shrink-0 text-xs text-[#60708a]">{formatDate(notification.occurred_at)}</time>
              </div>
              <p className="mt-2 text-sm leading-6 text-[#60708a] [overflow-wrap:anywhere]">{notification.message}</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-xs font-semibold text-[#60708a]">Delivery: {notification.delivery_status}</span>
                <Link href={notification.href} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full border border-[#bfd0e8] px-4 text-sm font-bold text-[#194f95] sm:w-fit">View update <ArrowRight aria-hidden="true" className="size-4" /></Link>
              </div>
            </div>
          </div>
        </article>)}
      </div>
    </section>}
  </StudentDashboardShell>;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg" }).format(date);
}
