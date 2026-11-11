import type { Metadata } from "next";
import { requireVerifiedStudent } from "@/lib/auth";
import { getSponsorDashboard, SponsorApiError, type SponsorDashboardData } from "@/lib/sponsor-api";
import { SponsorDashboard } from "@/components/site/sponsor/sponsor-dashboard";
import { prepareSponsorPayment } from "@/app/sponsor/payment-actions";
import { signOutAction } from "@/app/auth/actions";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Sponsor Dashboard",
  robots: { index: false, follow: false },
};

export default async function SponsorPage({ searchParams }: {
  searchParams: Promise<{ year?: string; page?: string; view?: string; payment_error?: string }>;
}) {
  await requireVerifiedStudent("/sponsor");
  const query = await searchParams;
  let data: SponsorDashboardData | null = null;
  let state: "ready" | "approval" | "unavailable" | "invalid" = "ready";
  try {
    data = await getSponsorDashboard(query.year, query.page);
  } catch (error) {
    state = error instanceof SponsorApiError && error.status === 403 ? "approval"
      : error instanceof SponsorApiError && error.status === 400 ? "invalid" : "unavailable";
  }
  return <SponsorDashboard data={data} state={state} initialView={query.view} signOutAction={signOutAction} paymentAction={prepareSponsorPayment} paymentKey={crypto.randomUUID()} paymentError={query.payment_error === "checkout"} />;
}
