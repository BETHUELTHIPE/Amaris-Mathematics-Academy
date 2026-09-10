import type { Metadata } from "next";
import { RecoveryPage } from "@/components/site/recovery-page";
import { experienceRecoveryDefinitions } from "@/lib/recovery";
import { safeRelativePath } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Session Expired", robots: { index: false, follow: false } };
export default async function SessionExpiredPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  const returnTo = safeRelativePath(next);
  const definition = {
    ...experienceRecoveryDefinitions["session-expired"],
    primaryAction: { label: "Log in securely", href: `/login?next=${encodeURIComponent(returnTo)}` },
  };
  return <RecoveryPage definition={definition} />;
}
