import Link from "next/link";
import { requireVerifiedStudent } from "@/lib/auth";
import { subscriptionSupport } from "@/lib/subscription-plans";
import { getSubscription } from "@/lib/subscription-api";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
export const dynamic = "force-dynamic";
export const metadata = { title: "Subscription payment status", robots: { index: false, follow: false } };
export default async function SubscriptionStatusPage({ searchParams }: { searchParams: Promise<{ reference?: string }> }) {
  const reference = (await searchParams).reference || "";
  await requireVerifiedStudent(`/subscriptions/status?reference=${encodeURIComponent(reference)}`);
  let item;
  try { item = await getSubscription(reference); } catch { /* Private unavailable state. */ }
  return <StudentDashboardShell active="subscriptions" title={item?.active ? "Your curriculum is ready." : "Your subscription status"} description="Payment status comes from the academy’s verified payment record."><div className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-9">
    {item ? <><h2 className="text-2xl font-semibold">{item.curriculum_label} · {item.months} months</h2><p className="mt-4 break-all text-sm text-[#60708a]">Reference: {item.reference}</p><p role="status" className="mt-5 text-lg font-semibold">{item.active ? "Payment confirmed · course access active" : item.status === "pending" ? "Awaiting payment confirmation. Refresh after completing payment." : item.status === "refunded" ? "Payment refunded or reversed · access inactive" : "Course access is inactive. Check your subscription dates or contact the academy."}</p>{item.gateway_mode === "sandbox" && <p className="mt-4 text-sm text-[#765314]">Test subscription · PayFast sandbox</p>}{item.active && <p className="mt-5 text-sm leading-7 text-[#60708a]">{subscriptionSupport.weeklySessions} · {subscriptionSupport.weeklyTotal}. {subscriptionSupport.scheduling}</p>}<div className="mt-7 flex flex-wrap gap-5">{item.active && <Link href="/contact" className="font-bold text-[#1f5bbd] underline">Arrange my included sessions</Link>}<Link href="/dashboard#my-courses" className="font-bold text-[#1f5bbd] underline">Open my courses</Link><Link href="/dashboard/subscriptions" className="font-bold text-[#1f5bbd] underline">My subscriptions</Link><Link href={`/subscriptions/status?reference=${item.reference}`} className="font-bold text-[#1f5bbd] underline">Refresh status</Link></div></> : <p role="alert" className="text-sm leading-7 text-[#60708a]">This subscription could not be loaded. Sign in with the account used at checkout and try again.</p>}
  </div></StudentDashboardShell>;
}
