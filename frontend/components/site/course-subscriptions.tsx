import Link from "next/link";
import { ArrowRight, Check, CalendarDays } from "lucide-react";
import { subscriptionPlans, subscriptionPrice, subscriptionSupport } from "@/lib/subscription-plans";
import { SubscriptionValue } from "@/components/site/subscription-value";

export function CourseSubscriptions() {
  return <section id="course-subscriptions" aria-labelledby="subscriptions-heading" className="mx-auto max-w-7xl scroll-mt-28 px-5 py-20 lg:px-8">
    <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:gap-14">
      <div className="lg:pt-5"><p className="eyebrow">Invest in your next chapter</p><h2 id="subscriptions-heading" className="section-title mt-4">Learn with a plan.<br />Progress with support.</h2><p className="mt-6 max-w-lg text-lg leading-8 text-[#60708a]">Choose four or eight months of live tutor support and course access in the curriculum you study. Two focused sessions each week help you turn study time into a steady routine.</p><p className="mt-5 text-sm font-semibold leading-7 text-[#31537e]">CAPS · IEB · TVET NATED · TVET NC(V) · University / UNISA</p><div className="mt-7 inline-flex items-center gap-3 rounded-2xl border border-[#dce4ef] bg-white px-5 py-4 text-sm font-semibold text-[#31537e]"><CalendarDays aria-hidden="true" className="size-5 shrink-0" />One upfront payment. No automatic renewal.</div></div>
      <div className="grid gap-5 sm:grid-cols-2">{subscriptionPlans.map(plan => {
        const dark = plan.months === 8;
        return <article key={plan.slug} className={`flex min-w-0 flex-col rounded-[1.8rem] border p-6 sm:p-7 ${dark ? "border-[#07152d] bg-[#07152d] text-white shadow-xl" : "border-[#dce4ef] bg-white text-[#07152d]"}`}>
          <p className={`text-xs font-bold uppercase tracking-[.14em] ${dark ? "text-[#ffcc66]" : "text-[#1f5bbd]"}`}>{plan.months}-month subscription</p><h3 className="mt-5 text-2xl font-semibold tracking-tight">{plan.title}</h3><p className={`mt-4 text-sm leading-7 ${dark ? "text-white/75" : "text-[#60708a]"}`}>{plan.description}</p><p className="mt-7 text-4xl font-semibold tracking-tight">{subscriptionPrice(plan.price)}</p><p className={`mt-2 text-sm ${dark ? "text-white/70" : "text-[#60708a]"}`}>Total for {plan.months} months · R950/month equivalent</p>
          <ul className="my-7 grid gap-3 text-sm leading-6">{[subscriptionSupport.weeklySessions, subscriptionSupport.weeklyTotal, "Published courses in your chosen curriculum", "Practice, revision and saved progress"].map(text => <li key={text} className="flex gap-2"><Check aria-hidden="true" className={`mt-1 size-4 shrink-0 ${dark ? "text-[#ffcc66]" : "text-[#13715f]"}`} />{text}</li>)}</ul><Link href={`/subscriptions/${plan.slug}`} className={`mt-auto inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-4 py-3 text-center text-sm font-bold ${dark ? "bg-[#ffcc66] text-[#07152d] hover:bg-[#ffd780]" : "bg-[#0b2a5b] text-white hover:bg-[#123d79]"}`}>Choose {plan.months} months<ArrowRight aria-hidden="true" className="size-4 shrink-0" /></Link>
        </article>;
      })}</div>
    </div><SubscriptionValue /><p className="mt-6 text-sm leading-7 text-[#60708a]">Included Zoom sessions support your selected curriculum throughout the paid term, at times arranged with the academy. Additional tutoring beyond these sessions and custom video requests are booked separately.</p>
  </section>;
}
