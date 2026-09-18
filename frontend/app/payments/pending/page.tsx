import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RecoveryPage } from "@/components/site/recovery-page";
import { getStudentIdentity } from "@/lib/auth";
import { experienceRecoveryDefinitions } from "@/lib/recovery";
import { getStudentPaymentStatus } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Payment Pending",
  robots: { index: false, follow: false },
};

export default async function PaymentPendingPage({
  searchParams,
}: {
  searchParams: Promise<{ reference?: string }>;
}) {
  const { reference } = await searchParams;
  let destination: string | null = null;

  if (reference && /^PF-[A-Za-z0-9_-]{8,80}$/.test(reference)) {
    const student = await getStudentIdentity();
    if (student?.emailVerified) {
      try {
        const payment = await getStudentPaymentStatus(reference);
        if (payment.status === "paid") destination = "/payments/confirmed";
        if (payment.status === "failed") destination = "/payments/failed";
        if (payment.status === "cancelled") destination = "/payments/cancelled";
      } catch {
        // Keep the safe pending state if the status service is temporarily unavailable.
      }
    }
  }

  if (destination) redirect(destination);
  return <RecoveryPage definition={experienceRecoveryDefinitions["payment-pending"]} />;
}
