import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseSubscriptions } from "@/components/site/course-subscriptions";
export const metadata = { title: "Course subscriptions", description: "Weekly tutor support and course access: four months for R3,800 or eight months for R7,600 in your chosen curriculum." };
export default function SubscriptionsPage() { return <main className="min-h-screen bg-[#f5f7fb]"><Header /><h1 className="sr-only">Choose your course subscription</h1><CourseSubscriptions /><Footer /></main>; }
