import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, CalendarDays, CheckCircle2 } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { EnquiryForm } from "@/components/site/enquiry-form";
import { getManagedCourses } from "@/lib/cms";
import { courseSubscriptionPlans, getCourseSubscriptionPlan, subscriptionRequestMessage } from "@/lib/course-subscriptions";

type PageProps = {
  params: Promise<{ duration: string }>;
  searchParams: Promise<{ course?: string | string[] }>;
};

export const dynamic = "force-dynamic";

export function generateStaticParams() {
  return courseSubscriptionPlans.map((plan) => ({ duration: plan.slug }));
}

export async function generateMetadata({ params }: Pick<PageProps, "params">): Promise<Metadata> {
  const plan = getCourseSubscriptionPlan((await params).duration);
  return plan ? {
    title: `${plan.months}-Month Course Subscription`,
    description: `Choose your mathematics course and request pricing for a ${plan.months}-month subscription with Amaris Mathematics Academy.`,
  } : {};
}

export default async function CourseSubscriptionPage({ params, searchParams }: PageProps) {
  const plan = getCourseSubscriptionPlan((await params).duration);
  if (!plan) notFound();
  const courses = await getManagedCourses();
  const query = await searchParams;
  const selectedSlug = typeof query.course === "string" ? query.course : "";
  const selectedCourse = courses.find((course) => course.slug === selectedSlug);
  const otherCourse = selectedSlug === "other";
  const hasSelection = Boolean(selectedCourse || otherCourse);
  const invalidSelection = Boolean(selectedSlug && !hasSelection);
  const message = hasSelection ? subscriptionRequestMessage(plan, selectedCourse ?? {
    title: "A course or module not listed below",
    curriculum: "Please help me choose",
    level: "I will include my grade, TVET level or university module in this message",
  }) : "";
  const alternative = courseSubscriptionPlans.find((item) => item.slug !== plan.slug)!;

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#0a1b36]">
      <Header />
      <section className="bg-[#07152d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-14 lg:px-8 lg:py-20">
          <Link href="/subscriptions" className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-white/80 hover:text-white"><ArrowLeft aria-hidden="true" className="size-4" /> Compare all plans</Link>
          <p className="mt-7 flex items-center gap-2 text-sm font-bold text-[#ffcc66]"><CalendarDays aria-hidden="true" className="size-4" /> {plan.months}-month study period</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold leading-tight tracking-[-.045em] sm:text-6xl">{plan.months}-month course subscription</h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-white/80">{plan.description}</p>
        </div>
      </section>
      <section className="mx-auto grid max-w-7xl items-start gap-8 px-5 py-12 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,.7fr)] lg:px-8 lg:py-16">
        <div className="min-w-0 space-y-7">
          <div className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8">
            <p className="eyebrow">Step 1 · Your course</p>
            <h2 className="mt-3 text-2xl font-semibold">What would you like to study?</h2>
            <p id="subscription-course-help" className="mt-3 text-sm leading-7 text-[#60708a]">Choose an available course, or ask us about a different curriculum, grade or module.</p>
            {invalidSelection && <p className="mt-4 rounded-xl bg-[#fff3f1] p-4 text-sm text-[#8f2d24]" role="alert">That course is not listed. Please choose a course below or select “Help me find my course”.</p>}
            <form method="get" action={`/subscriptions/${plan.slug}`} className="mt-6">
              <label htmlFor="subscription-course" className="text-sm font-semibold">Course <span aria-hidden="true">*</span></label>
              <select id="subscription-course" name="course" required defaultValue={hasSelection ? selectedSlug : ""} aria-describedby="subscription-course-help" className="mt-2 min-h-12 w-full min-w-0 max-w-full rounded-xl border border-[#cdd8e6] bg-[#fbfcfe] px-3 text-base">
                <option value="" disabled>Select a course</option>
                {courses.map((course) => <option key={course.slug} value={course.slug}>{course.title} · {course.level}</option>)}
                <option value="other">Help me find my course</option>
              </select>
              <button type="submit" className="mt-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white hover:bg-[#16427e] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2767d8]">{hasSelection ? "Update course" : "Continue with this course"} <ArrowRight aria-hidden="true" className="size-4" /></button>
            </form>
          </div>
          <div id="subscription-request" className="relative min-w-0 overflow-hidden rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8">
            <p className="eyebrow">Step 2 · Your request</p>
            <h2 className="mt-3 text-2xl font-semibold">Let’s confirm your study plan.</h2>
            {hasSelection ? <>
              <p className="mt-3 text-sm leading-7 text-[#60708a]">Your {plan.months}-month plan and course have been added to the message. Review it, add any study goals and send your request to Amaris.</p>
              <EnquiryForm key={`${plan.slug}:${selectedSlug}`} initialEnquiryType="course-guidance" initialMessage={message} draftKey={`subscription-${plan.slug}-${selectedSlug}`} />
            </> : <p className="mt-4 rounded-2xl bg-[#edf3ff] p-5 text-sm leading-7 text-[#46556e]">Choose your course in step 1 to open the subscription request form.</p>}
          </div>
        </div>
        <aside aria-labelledby="subscription-summary-title" className="min-w-0 rounded-3xl bg-[#0b2a5b] p-7 text-white lg:sticky lg:top-36">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Your selected plan</p>
          <h2 id="subscription-summary-title" className="mt-5 text-4xl font-semibold tracking-tight">{plan.months} months</h2>
          <p className="mt-3 text-lg font-semibold">{plan.title}</p>
          <dl className="mt-7 space-y-5 border-y border-white/20 py-6">
            <div><dt className="text-xs font-semibold uppercase tracking-wider text-white/70">Course</dt><dd className="mt-2 break-words text-base">{selectedCourse?.title ?? (otherCourse ? "Course guidance requested" : "Choose a course in step 1")}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wider text-white/70">Price</dt><dd className="mt-2 text-base text-[#ffcc66]">Confirmed before payment</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wider text-white/70">Access dates & content</dt><dd className="mt-2 text-sm leading-6 text-white/85">Agreed with Amaris for your chosen course.</dd></div>
          </dl>
          <p className="mt-6 flex items-start gap-3 text-sm leading-7 text-white/85"><CheckCircle2 aria-hidden="true" className="mt-1 size-5 shrink-0 text-[#ffcc66]" />Submitting this request does not activate a subscription or take payment.</p>
          <Link href={`/subscriptions/${alternative.slug}${hasSelection ? `?course=${encodeURIComponent(selectedSlug)}` : ""}`} className="mt-6 inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#ffcc66] hover:underline">Prefer {alternative.months} months? <ArrowRight aria-hidden="true" className="size-4" /></Link>
          <Link href="/payment-policy" className="mt-2 block min-h-11 py-3 text-sm text-white/80 underline underline-offset-4">Read the payment policy</Link>
        </aside>
      </section>
      <Footer />
    </main>
  );
}
