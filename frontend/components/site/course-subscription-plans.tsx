import Link from "next/link";
import { ArrowRight, BookOpenCheck, CalendarDays, Check } from "lucide-react";
import { courseSubscriptionPlans } from "@/lib/course-subscriptions";

export function CourseSubscriptionPlans() {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {courseSubscriptionPlans.map((plan) => {
        const extended = plan.months === 8;
        return (
          <article key={plan.slug} className={`relative flex min-w-0 flex-col overflow-hidden rounded-[2rem] border p-7 sm:p-9 ${extended ? "border-[#0b2a5b] bg-[#0b2a5b] text-white shadow-[0_20px_55px_rgba(7,21,45,.12)]" : "border-[#dce4ef] bg-white text-[#0a1b36]"}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold ${extended ? "bg-white/10 text-[#ffcc66]" : "bg-[#edf3ff] text-[#1f5bbd]"}`}>
                <CalendarDays aria-hidden="true" className="size-4" /> {plan.months}-month plan
              </span>
              <span className={`text-xs font-semibold ${extended ? "text-white/75" : "text-[#60708a]"}`}>{plan.focus}</span>
            </div>
            <p className="mt-9 flex items-baseline gap-2"><span className="text-6xl font-semibold tracking-[-.06em]">{plan.months}</span><span className={`text-xl ${extended ? "text-white/75" : "text-[#60708a]"}`}>months</span></p>
            <h3 className="mt-4 text-2xl font-semibold tracking-tight">{plan.title}</h3>
            <p className={`mt-3 max-w-lg text-base leading-7 ${extended ? "text-white/80" : "text-[#60708a]"}`}>{plan.description}</p>
            <ul className="mt-7 grid gap-3 text-sm">
              {["Choose your mathematics course", "Tell us your curriculum and study level", "Receive the price and access details before payment"].map((item) => (
                <li key={item} className="flex items-start gap-3"><Check aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${extended ? "text-[#ffcc66]" : "text-[#1f5bbd]"}`} /><span>{item}</span></li>
              ))}
            </ul>
            <div className={`mt-8 border-t pt-6 ${extended ? "border-white/20" : "border-[#dce4ef]"}`}>
              <p className={`flex items-center gap-2 text-sm font-semibold ${extended ? "text-[#ffcc66]" : "text-[#1f5bbd]"}`}><BookOpenCheck aria-hidden="true" className="size-4" /> Request course-specific pricing</p>
              <Link href={`/subscriptions/${plan.slug}`} className={`mt-5 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full px-5 py-3 text-center font-bold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2767d8] ${extended ? "bg-[#ffcc66] text-[#07152d] hover:bg-[#ffd780]" : "bg-[#0b2a5b] text-white hover:bg-[#16427e]"}`}>
                Choose {plan.months} months <ArrowRight aria-hidden="true" className="size-4 shrink-0" />
              </Link>
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function HomeCourseSubscriptions() {
  return (
    <section id="course-subscriptions" aria-labelledby="course-subscriptions-title" className="border-y border-[#dce4ef] bg-[#edf2fa]">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-24">
        <div className="mb-10 flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div><p className="eyebrow">Course subscriptions</p><h2 id="course-subscriptions-title" className="section-title mt-3 max-w-2xl">Make time for your<br className="hidden sm:block" /> next breakthrough.</h2><p className="mt-5 max-w-2xl text-lg leading-8 text-[#60708a]">Choose a 4-month or 8-month study period. Find your course, request your plan and get clear access details before you commit.</p></div>
          <Link href="/subscriptions" className="inline-flex min-h-11 shrink-0 items-center gap-2 font-bold text-[#1f5bbd] hover:underline">Compare subscription plans <ArrowRight aria-hidden="true" className="size-4" /></Link>
        </div>
        <CourseSubscriptionPlans />
        <p className="mt-6 text-center text-sm leading-6 text-[#60708a]">Prices and course coverage are confirmed by the Amaris team. Sending a request does not take payment or activate access.</p>
      </div>
    </section>
  );
}
