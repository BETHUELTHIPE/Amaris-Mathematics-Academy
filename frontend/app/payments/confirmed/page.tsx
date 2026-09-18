import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RecoveryPage } from "@/components/site/recovery-page";
import { experienceRecoveryDefinitions } from "@/lib/recovery";
import { getStudentPaymentStatus } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Payment Confirmed",
  robots: { index: false, follow: false },
};

export default async function PaymentConfirmedPage({
  searchParams,
}: {
  searchParams: Promise<{ reference?: string }>;
}) {
  const reference = (await searchParams).reference;
  if (!reference || !/^[A-Za-z0-9_-]{1,100}$/.test(reference)) {
    redirect("/dashboard");
  }

  let payment;
  try {
    payment = await getStudentPaymentStatus(reference);
  } catch {
    redirect(`/payments/pending?reference=${encodeURIComponent(reference)}`);
  }

  if (payment.status !== "paid" || payment.enrollment_status !== "active") {
    redirect(`/payments/pending?reference=${encodeURIComponent(reference)}`);
  }

  return <RecoveryPage definition={experienceRecoveryDefinitions["payment-confirmed"]} />;
}
