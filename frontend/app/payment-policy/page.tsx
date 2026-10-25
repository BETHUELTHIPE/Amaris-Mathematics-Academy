import type { Metadata } from "next";
import { PolicyPage } from "@/components/site/policy-page";

export const metadata: Metadata = {
  title: "Payment Policy",
  description: "Amaris Mathematics Academy prices, checkout, course access, cancellations and refunds.",
};

export default function PaymentPolicyPage() {
  return <PolicyPage policyKey="payment" />;
}
