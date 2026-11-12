import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenCheck, CalendarDays, MessageCircle } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseSubscriptionPlans } from "@/components/site/course-subscription-plans";

export const metadata: Metadata = {
  title: "Course Subscriptions | 4 or 8 Months",
  description: "Explore 4-month and 8-month mathematics course subscriptions. Select your study period and request course-specific pricing from Amaris Mathematics Academy.",
};

export default function CourseSubscriptionsPage() {
  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="bg-[#07152d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-24">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Your course. Your study period.</p>
          <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-tight tracking-[-.045em] sm:text-6xl">Small steps.<br /><span className="text-[#ffcc66]">Lasting mathematics confidence.</span></h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-white/80">Choose four months for a focused goal or eight months for a longer learning journey. Start by finding the plan that fits your studies.</p>
          <a href="#plans" className="mt-8 inline-flex min-h-12 items-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3 font-bold text-[#07152d]">Explore the plans <ArrowRight aria-hidden="true" className="size-4" /></a>
        </div>
      </section>
      <section id="plans" aria-labelledby="plans-title" className="mx-auto max-w-7xl scroll-mt-36 px-5 py-16 lg:px-8 lg:py-20">
        <div className="mb-9"><p className="eyebrow">Choose your duration</p><h2 id="plans-title" className="section-title mt-3">A study plan with room to grow.</h2><p className="mt-5 max-w-2xl text-base leading-7 text-[#60708a]">Select a plan to choose your course and send a subscription request. We will confirm the full price, included content and access dates before you pay.</p></div>
        <CourseSubscriptionPlans />
      </section>
      <section aria-labelledby="subscription-steps-title" className="mx-auto max-w-7xl px-5 pb-20 lg:px-8">
        <h2 id="subscription-steps-title" className="text-3xl font-semibold tracking-tight">Your next three steps</h2>
        <ol className="mt-8 grid gap-5 md:grid-cols-3">
          {[
            { Icon: CalendarDays, title: "Choose your study period", copy: "Select the 4-month or 8-month plan that suits your learning goal." },
            { Icon: BookOpenCheck, title: "Find your course", copy: "Choose your course or tell us the curriculum, grade or university module you need." },
            { Icon: MessageCircle, title: "Confirm your plan", copy: "Send your request. Review the price, access dates, payment options and terms with the Amaris team." },
          ].map(({ Icon, title, copy }, index) => <li key={title} className="rounded-3xl border border-[#dce4ef] bg-white p-6"><div className="flex items-center justify-between"><Icon aria-hidden="true" className="size-6 text-[#1f5bbd]" /><span className="text-sm font-semibold text-[#60708a]">0{index + 1}</span></div><h3 className="mt-6 text-xl font-semibold">{title}</h3><p className="mt-3 text-sm leading-7 text-[#60708a]">{copy}</p></li>)}
        </ol>
        <div className="mt-12 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9">
          <h2 className="text-2xl font-semibold">Before you subscribe</h2>
          <div className="mt-5 divide-y divide-[#dce4ef]">
            {[
              ["How much does a plan cost?", "Pricing depends on the course and duration. Request your plan for the full price in South African rand before making payment."],
              ["Does a plan cover every course?", "Course coverage must be confirmed for your chosen plan. Do not assume a subscription includes the whole catalogue or private tutoring."],
              ["When does access start and end?", "The Amaris team will confirm your access start and end dates, included lessons and renewal terms before you pay."],
              ["Will sending a request charge me?", "No. This is a subscription enquiry. Sending it does not take payment, activate access or start automatic billing."],
            ].map(([question, answer]) => <details key={question} className="group py-4"><summary className="min-h-11 cursor-pointer py-2 font-semibold marker:text-[#1f5bbd]">{question}</summary><p className="max-w-3xl pb-2 text-sm leading-7 text-[#60708a]">{answer}</p></details>)}
          </div>
          <Link href="/courses" className="mt-6 inline-flex min-h-11 items-center gap-2 font-bold text-[#1f5bbd] hover:underline">Browse all courses <ArrowRight aria-hidden="true" className="size-4" /></Link>
        </div>
      </section>
      <Footer />
    </main>
  );
}
