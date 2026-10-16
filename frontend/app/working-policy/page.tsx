import type { Metadata } from "next";
import { PolicyPage } from "@/components/site/policy-page";

export const metadata: Metadata = { title: "How We Work Policy" };
export default function WorkingPolicyPage() { return <PolicyPage kind="working" />; }
