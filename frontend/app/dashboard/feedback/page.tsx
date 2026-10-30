import { requireVerifiedStudent } from "@/lib/auth";
import { FeedbackForm } from "./feedback-form";

export const metadata = { title: "Happy Form | Amaris Mathematics Academy", robots: { index: false, follow: false } };

export default async function FeedbackPage() {
  await requireVerifiedStudent("/dashboard/feedback");
  return <main className="min-h-screen bg-slate-50 px-4 py-12"><FeedbackForm /></main>;
}
