import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { subscriptionPlan, subscriptionCurricula, subscriptionPrice } from "@/lib/subscription-plans";

export async function generateMetadata({ params }: { params: Promise<{ plan: string }> }) {
  const plan = subscriptionPlan((await params).plan);
  return { title: plan ? `${plan.months}-month course subscription — ${subscriptionPrice(plan.price)}` : "Subscription not found" };
}
export default async function SubscriptionPlanPage({ params }: { params: Promise<{ plan: string }> }) {
  const plan = subscriptionPlan((await params).plan);
  if (!plan) notFound();
  return <main className="min-h-screen bg-[#f5f7fb] text-[#07152d]"><Header />
    <section className="bg-[#07152d] text-white"><div className="mx-auto max-w-7xl px-5 py-12 sm:py-16 lg:px-8"><Link href="/subscriptions" className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-white/75"><ArrowLeft className="size-4" />Compare plans</Link><p className="mt-7 text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Your next chapter · {plan.months} months</p><h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight tracking-[-.04em] sm:text-6xl">{plan.title}.</h1><p className="mt-6 max-w-2xl text-lg leading-8 text-white/75">A dedicated course subscription for the curriculum you choose. Make room for steady learning, guided practice and revision.</p></div></section>
    <div className="mx-auto grid max-w-7xl gap-8 px-5 py-12 lg:grid-cols-[1.35fr_.75fr] lg:px-8 lg:py-16">
      <form action={`/subscriptions/${plan.slug}/checkout`} method="get" className="min-w-0 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-9"><p className="eyebrow">Step 1 of 2</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Choose your curriculum</h2><p id="curriculum-help" className="mt-4 text-sm leading-7 text-[#60708a]">Select one curriculum to continue. Your choice will appear on your order and determines which published courses you can access.</p>
        <fieldset className="mt-7 grid gap-3" aria-describedby="curriculum-help"><legend className="sr-only">Curriculum (required)</legend>{subscriptionCurricula.map(curriculum => <label key={curriculum.value} className="flex min-h-20 cursor-pointer items-center gap-4 rounded-2xl border border-[#dce4ef] p-4 transition hover:border-[#1f5bbd] has-[:checked]:border-[#1f5bbd] has-[:checked]:bg-[#edf3ff] focus-within:ring-2 focus-within:ring-[#1f5bbd]"><input type="radio" name="curriculum" value={curriculum.value} required className="size-5 shrink-0 accent-[#1f5bbd]" /><span><span className="block font-bold">{curriculum.label}</span><span className="mt-1 block text-sm text-[#60708a]">{curriculum.description}</span></span></label>)}</fieldset>
        <button type="submit" className="mt-7 inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white hover:bg-[#123d79]">Continue with my curriculum<ArrowRight aria-hidden="true" className="size-4" /></button><p className="mt-4 flex items-center gap-2 text-sm leading-6 text-[#60708a]"><ShieldCheck aria-hidden="true" className="size-4 shrink-0" />Sign in and verify your email before payment.</p>
      </form>
      <aside className="h-fit rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:sticky lg:top-32"><p className="text-sm font-bold text-[#1f5bbd]">Your study plan</p><h2 className="mt-4 text-2xl font-semibold">{plan.months}-month course access</h2><p className="mt-6 text-5xl font-semibold tracking-tight">{subscriptionPrice(plan.price)}</p><p className="mt-2 text-sm text-[#60708a]">One upfront payment in South African rand</p><ul className="mt-7 grid gap-4 text-sm leading-7">{[`Access for ${plan.months} calendar months after verified payment`, "The same price for every curriculum", "Published courses in one selected curriculum", "Your learning progress stays saved", "No automatic renewal"].map(text => <li key={text} className="flex gap-3"><CheckCircle2 aria-hidden="true" className="mt-1 size-4 shrink-0 text-[#13715f]" />{text}</li>)}</ul><p className="mt-7 border-t border-[#dce4ef] pt-5 text-sm leading-7 text-[#60708a]">Live tutoring, Zoom sessions and custom video requests are separate services. Subscription access ends when your paid term expires.</p><Link href={`/subscriptions/${plan.months === 4 ? "8-months" : "4-months"}`} className="mt-5 inline-block min-h-11 py-2 text-sm font-bold text-[#1f5bbd] underline">Explore the {plan.months === 4 ? "eight" : "four"}-month plan</Link></aside>
    </div><Footer />
  </main>;
}
