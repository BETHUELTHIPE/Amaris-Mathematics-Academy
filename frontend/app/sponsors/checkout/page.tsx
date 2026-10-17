import Link from "next/link";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { createSandboxSponsorship } from "@/lib/sponsorship-sandbox";

export const dynamic = "force-dynamic";
export const metadata = { title: "Test sponsorship checkout | Amaris", robots: { index: false, follow: false } };

export default async function SponsorCheckout({ searchParams }: { searchParams: Promise<{ amount?: string }> }) {
  const { amount } = await searchParams;
  let checkout: ReturnType<typeof createSandboxSponsorship> | null = null;
  try {
    checkout = createSandboxSponsorship(amount ?? "", process.env.SITE_URL || process.env.RENDER_EXTERNAL_URL || "https://amaris-mathematics-academy-live-students.onrender.com");
  } catch { /* Invalid amounts and incomplete merchant configuration never create a form. */ }
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-2xl px-5 py-16"><Link href="/sponsors#contribute" className="font-semibold text-[#1f5bbd]">← Back to sponsorship</Link><div className="mt-8 rounded-3xl border border-[#dce4ef] bg-white p-8"><p className="eyebrow">Development sandbox</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">Test your contribution.</h1><p className="mt-5 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm leading-7 text-[#765314]">Test payments only. No real money will be charged or sent to the academy. This demonstration does not issue a receipt or record a verified contribution.</p>{checkout ? <><p className="mt-6 text-3xl font-bold">R{checkout.fields.amount} <span className="text-sm font-normal text-[#60708a]">ZAR · simulated sponsorship</span></p><form method="post" action={checkout.gatewayUrl} className="mt-7">{Object.entries(checkout.fields).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}<button className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-6 py-4 font-bold text-white" type="submit">Continue to PayFast sandbox</button></form><p className="mt-4 text-xs leading-6 text-[#60708a]">Use PayFast sandbox test payment details only.</p></> : <p role="alert" className="mt-6 leading-7 text-[#60708a]">Checkout is unavailable. Choose a test amount between R5 and R100,000 on the sponsorship page. If this continues, contact the academy.</p>}</div></section><Footer /></main>;
}
