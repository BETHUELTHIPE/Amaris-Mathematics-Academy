import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RecoveryPage } from "@/components/site/recovery-page";
import { experienceRecoveryDefinitions } from "@/lib/recovery";
import { getStudentPaymentStatus } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Payment Pending",
  robots: { index: false, follow: false },
};

function validReference(value: string | undefined): string | null {
  if (!value || !/^[A-Za-z0-9_-]{1,100}$/.test(value)) return null;
  return value;
}

export default async function PaymentPendingPage({
  searchParams,
}: {
  searchParams: Promise<{ reference?: string }>;
}) {
  const reference = validReference((await searchParams).reference);

  if (reference) {
    try {
      const payment = await getStudentPaymentStatus(reference);
      if (payment.status === "paid" && payment.enrollment_status === "active") {
        redirect(`/payments/confirmed?reference=${encodeURIComponent(reference)}`);
      }
      if (payment.status === "failed") {
        redirect(`/payments/failed?reference=${encodeURIComponent(reference)}`);
      }
      if (payment.status === "cancelled" || payment.status === "refunded") {
        redirect(`/payments/cancelled?reference=${encodeURIComponent(reference)}`);
      }
    } catch {
      // Keep the student in the safe pending state if the status service is
      // temporarily unavailable. Never infer success from the browser return.
    }
  }

  return <>
    <RecoveryPage definition={experienceRecoveryDefinitions["payment-pending"]} />
    {reference ? (
      <script
        dangerouslySetInnerHTML={{
          __html: "window.setTimeout(() => window.location.reload(), 5000);",
        }}
      />
    ) : null}
  </>;
}
