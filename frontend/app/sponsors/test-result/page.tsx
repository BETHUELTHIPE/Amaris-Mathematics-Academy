import Link from "next/link";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
export const metadata = { title: "Sandbox return | Amaris", robots: { index: false, follow: false } };
export default async function TestResult({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const cancelled = (await searchParams).state === "cancelled";
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-2xl px-5 py-20"><div className="rounded-3xl border border-[#dce4ef] bg-white p-8"><p className="eyebrow">PayFast sandbox</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">{cancelled ? "Test checkout cancelled." : "You’re back from test checkout."}</h1><p className="mt-5 leading-8 text-[#60708a]">No real money has moved. This return page does not confirm a payment. Check your PayFast sandbox dashboard for the test transaction result.</p><Link href="/sponsors#contribute" className="mt-7 inline-flex rounded-full bg-[#0b2a5b] px-6 py-4 font-bold text-white">Back to sponsorship</Link></div></section><Footer /></main>;
}
