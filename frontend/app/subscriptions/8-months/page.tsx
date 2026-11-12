import type { Metadata } from "next";
import { CourseSubscriptionPage } from "@/components/site/course-subscription-page";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "8-Month Course Subscription",
  description: "Choose your mathematics course and request pricing for a 8-month subscription with Amaris Mathematics Academy.",
};

export default function Subscription8MonthsPage({
  searchParams,
}: {
  searchParams: Promise<{ course?: string | string[] }>;
}) {
  return <CourseSubscriptionPage duration="8-months" searchParams={searchParams} />;
}
