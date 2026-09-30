import type { Metadata } from "next";
import { PolicyPage } from "@/components/site/policy-page";

export const metadata: Metadata = {
  title: "How We Work and Learn",
  description: "How Amaris Mathematics Academy students join, study, get support and use the learning service.",
};

export default function HowWeWorkPage() {
  return <PolicyPage policyKey="working" />;
}
