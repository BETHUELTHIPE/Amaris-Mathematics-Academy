import type { Metadata } from "next";
import { Suspense } from "react";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { AnalyticsDashboard, AnalyticsUnavailable } from "@/components/site/analytics-dashboard";
import { requireVerifiedStudent } from "@/lib/auth";
import { analyticsDays } from "@/lib/analytics";
import { getStudentAnalytics } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "My Analytics — Amaris", robots: { index: false, follow: false } };

async function StudentAnalyticsContent({ days, scope }: { days: 7 | 30 | 90; scope: string }) {
  let data;
  try { data = await getStudentAnalytics(days); }
  catch { return <AnalyticsUnavailable role="student" />; }
  return <AnalyticsDashboard data={data} preferenceScope={scope} />;
}

export default async function StudentAnalyticsPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const identity = await requireVerifiedStudent("/dashboard/analytics");
  const days = analyticsDays((await searchParams).days);
  return <StudentDashboardShell active="analytics" title="Your learning. A little clearer." description="A private view of your learning activity, with visuals that make sense to you.">
    <Suspense fallback={<div role="status" className="min-h-96 rounded-2xl border border-[#dce4ef] bg-white p-8 text-[#60708a]">Loading your private learning insights…</div>}><StudentAnalyticsContent days={days} scope={identity.id} /></Suspense>
  </StudentDashboardShell>;
}
