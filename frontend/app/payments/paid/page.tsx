import type { Metadata } from "next";
import { RecoveryPage } from "@/components/site/recovery-page";
import { experienceRecoveryDefinitions } from "@/lib/recovery";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Payment Confirmed", robots: { index: false, follow: false } };
export default function PaymentStatePage() { return <RecoveryPage definition={experienceRecoveryDefinitions["payment-paid"]} />; }
