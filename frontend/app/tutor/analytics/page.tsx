import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { BarChart3, LayoutDashboard, ShieldCheck } from "lucide-react";
import { AnalyticsDashboard, AnalyticsUnavailable } from "@/components/site/analytics-dashboard";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getStudentIdentity } from "@/lib/auth";
import { analyticsDays } from "@/lib/analytics";
import { getTutorAnalytics, TutorApiError } from "@/lib/tutor-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Tutor Analytics — Amaris", robots: { index: false, follow: false } };

export default async function TutorAnalyticsPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const identity = await getStudentIdentity();
  if (!identity) redirect("/tutor/login");
  if (!identity.emailVerified) redirect(`/tutor/verify-email?email=${encodeURIComponent(identity.email)}`);
  const days = analyticsDays((await searchParams).days);
  let data;
  let denied = false;
  try { data = await getTutorAnalytics(days); }
  catch (error) { denied = error instanceof TutorApiError && [401, 403].includes(error.status); }
  return <main className="min-h-screen min-w-0 bg-[#f5f7fb]"><Header />
    <section className="border-b border-[#dce4ef] bg-white"><div className="mx-auto max-w-7xl px-4 py-9 sm:px-6 lg:px-8"><p className="eyebrow">Private tutor workspace</p><h1 className="mt-3 text-3xl font-semibold tracking-[-.045em] sm:text-5xl">Your impact, in perspective.</h1><p className="mt-4 max-w-2xl text-[#60708a]">A clear view of your teaching activity and recorded earnings. Choose how you see it.</p><nav className="mt-7 flex flex-wrap gap-3" aria-label="Tutor workspace"><Link className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#dce4ef] px-4 text-sm font-semibold text-[#31537e]" href="/tutor/dashboard"><LayoutDashboard size={16} /> Overview</Link><Link className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#0b2a5b] px-4 text-sm font-semibold text-white" href="/tutor/analytics" aria-current="page"><BarChart3 size={16} /> Analytics</Link><Link className="inline-flex min-h-11 items-center rounded-xl border border-[#dce4ef] px-4 text-sm font-semibold text-[#31537e]" href="/tutor/dashboard#earnings">Earnings &amp; payouts</Link></nav></div></section>
    <section className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-10 lg:px-8">{denied ? <div className="max-w-xl rounded-2xl border border-[#dce4ef] bg-white p-8"><ShieldCheck className="text-[#205bd7]" size={32} /><h2 className="mt-5 text-2xl font-semibold">Tutor approval is required</h2><p className="mt-3 leading-7 text-[#60708a]">Analytics are available only to verified, approved tutors. Contact the academy if your tutor account needs approval.</p></div> : data ? <AnalyticsDashboard data={data} preferenceScope={identity.id} /> : <AnalyticsUnavailable role="tutor" />}</section><Footer />
  </main>;
}
