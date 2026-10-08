import type { Metadata } from "next";
import { PolicyPage } from "@/components/site/policy-page";

export const metadata: Metadata = { title: "Payment Policy" };
export default function PaymentPolicyPage() { return <PolicyPage kind="payment" />; }
