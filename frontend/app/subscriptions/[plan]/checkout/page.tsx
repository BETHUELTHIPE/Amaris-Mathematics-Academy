import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { createSubscriptionCheckout } from "@/lib/subscription-api";
import { subscriptionPlan, subscriptionCurriculum, subscriptionPrice, subscriptionSupport } from "@/lib/subscription-plans";

export const dynamic = "force-dynamic";
export const metadata = { title: "Confirm your course subscription", robots: { index: false, follow: false } };
export default async function SubscriptionCheckoutPage({ params, searchParams }: { params: Promise<{ plan: string }>; searchParams: Promise<{ curriculum?: string }> }) {
  const plan = subscriptionPlan((await params).plan);
  if (!plan) notFound();
  const curriculum = subscriptionCurriculum((await searchParams).curriculum || "");
  if (!curriculum) redirect(`/subscriptions/${plan.slug}`);
  await requireVerifiedStudent(`/subscriptions/${plan.slug}/checkout?curriculum=${curriculum.value}`);
  let checkout;
  try { checkout = await createSubscriptionCheckout(curriculum.value, plan.months); } catch { /* Redacted retry state. */ }
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-2xl px-5 py-12 sm:py-20"><Link href={`/subscriptions/${plan.slug}`} className="inline-flex min-h-11 items-center gap-2 text-sm font-bold text-[#1f5bbd]"><ArrowLeft className="size-4" />Change curriculum</Link><div className="mt-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-10"><p className="eyebrow">Step 2 of 2</p><h1 className="mt-4 text-3xl font-semibold tracking-tight">Confirm your subscription</h1><dl className="mt-7 grid gap-5 border-y border-[#dce4ef] py-6">{[["Curriculum", curriculum.label], ["Duration", `${plan.months} calendar months`], ["Weekly tutor support", "2 sessions × 30 minutes"], ["Weekly total", "1 hour on Zoom"], ["Total upfront", subscriptionPrice(plan.price)]].map(([label,value]) => <div key={label} className="flex flex-wrap justify-between gap-2"><dt className="text-[#60708a]">{label}</dt><dd className="font-bold">{value}</dd></div>)}</dl>
    {checkout ? <>{checkout.subscription.gateway_mode === "sandbox" && <p role="status" className="mt-6 rounded-xl bg-[#fff3d6] p-4 text-sm text-[#765314]">Test checkout · PayFast sandbox</p>}<p className="mt-6 text-sm leading-7 text-[#60708a]">Your plan includes two 30-minute Zoom sessions every week and published course access in your selected curriculum. Your term starts after payment verification. One upfront payment and no automatic renewal.</p><form method="post" action={checkout.gateway_url} className="mt-7">{Object.entries(checkout.fields).map(([name,value]) => <input key={name} type="hidden" name={name} value={value} />)}<button type="submit" className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white">Pay {subscriptionPrice(plan.price)} with PayFast</button></form><p className="mt-4 break-all text-xs text-[#60708a]">Order reference: {checkout.subscription.reference}</p></> : <div role="alert" className="mt-6 rounded-2xl bg-[#fff3d6] p-5 text-sm leading-7 text-[#765314]">Subscription checkout is temporarily unavailable, or you already have an active plan for this curriculum. <Link href="/dashboard/subscriptions" className="font-bold underline">View your subscriptions</Link> or try again shortly.</div>}
    <p className="mt-6 text-sm leading-7 text-[#60708a]">{subscriptionSupport.scheduling} Included sessions have no additional tutoring fee.</p><p className="mt-6 flex items-center gap-2 text-sm text-[#60708a]"><ShieldCheck aria-hidden="true" className="size-4 shrink-0" />Payment details are entered on PayFast.</p></div></section><Footer /></main>;
}
