import Link from "next/link";
import { requireVerifiedStudent } from "@/lib/auth";
import { subscriptionSupport } from "@/lib/subscription-plans";
import { getSubscriptions } from "@/lib/subscription-api";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
export const dynamic = "force-dynamic";
export const metadata = { title: "My subscriptions", robots: { index: false, follow: false } };
function date(value: string | null) { return value ? new Date(value).toLocaleDateString("en-ZA", { timeZone: "Africa/Johannesburg", day: "numeric", month: "long", year: "numeric" }) : "After verified payment"; }
export default async function MySubscriptionsPage() {
  await requireVerifiedStudent("/dashboard/subscriptions");
  let items: Awaited<ReturnType<typeof getSubscriptions>> = [];
  let unavailable = false;
  try { items = await getSubscriptions(); } catch { unavailable = true; }
  return <StudentDashboardShell active="subscriptions" title="Your curriculum subscriptions" description="Your chosen curriculum, payment status and access dates in one place."><Link href="/subscriptions" className="mb-6 inline-flex min-h-11 items-center rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Explore course plans</Link>
    {unavailable ? <p role="alert" className="rounded-2xl bg-[#fff3d6] p-6 text-sm text-[#765314]">Subscriptions are temporarily unavailable. Please try again shortly.</p> : !items.length ? <p className="rounded-3xl border border-[#dce4ef] bg-white p-8 text-[#60708a]">You have no course subscriptions yet. Choose a plan and curriculum to get started.</p> : <div className="grid gap-5">{items.map(item => <article key={item.reference} className="min-w-0 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8"><div className="flex flex-wrap justify-between gap-4"><h2 className="text-2xl font-semibold">{item.curriculum_label} · {item.months} months</h2><span className="rounded-full bg-[#edf3ff] px-4 py-2 text-sm font-bold text-[#1f5bbd]">{item.active ? "Active" : item.status === "pending" ? "Awaiting payment" : item.status === "refunded" ? "Refunded" : "Expired"}</span></div><p className="mt-4 text-sm leading-7 text-[#60708a]">R{Number(item.amount).toLocaleString("en-ZA")} · {date(item.starts_at)} – {date(item.ends_at)}</p>{item.gateway_mode === "sandbox" && <p className="mt-2 text-sm text-[#765314]">Test subscription</p>}<p className="mt-4 text-sm leading-7 text-[#60708a]">{subscriptionSupport.weeklySessions} · {subscriptionSupport.weeklyTotal}. {item.active && "Contact the academy with your reference to arrange your included sessions."}</p><p className="mt-2 break-all text-xs text-[#60708a]">{item.reference}</p><div className="mt-5 flex flex-wrap gap-5">{item.active && <Link href="/contact" className="font-semibold text-[#1f5bbd] underline">Arrange my included sessions</Link>}<Link href={`/subscriptions/status?reference=${item.reference}`} className="font-semibold text-[#1f5bbd] underline">Payment status</Link>{item.status === "paid" && <a href={`/api/subscriptions/${item.reference}/invoice`} className="font-semibold text-[#1f5bbd] underline">Download invoice PDF</a>}</div></article>)}</div>}
  </StudentDashboardShell>;
}
