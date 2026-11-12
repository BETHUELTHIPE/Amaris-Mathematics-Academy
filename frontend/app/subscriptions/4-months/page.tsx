import type { Metadata } from "next";
import { CourseSubscriptionPage } from "@/components/site/course-subscription-page";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "4-Month Course Subscription",
  description: "Choose your mathematics course and request pricing for a 4-month subscription with Amaris Mathematics Academy.",
};

export default function Subscription4MonthsPage({
  searchParams,
}: {
  searchParams: Promise<{ course?: string | string[] }>;
}) {
  return <CourseSubscriptionPage duration="4-months" searchParams={searchParams} />;
}
