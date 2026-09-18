import type { Metadata } from "next";
import Link from "next/link";
import { CreditCard, ShieldCheck } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Secure Checkout", robots: { index: false, follow: false } };

type CheckoutPayload = {
  reference: string;
  gateway_url: string;
  fields: Record<string, string>;
  state: string;
};

function assertPayFastUrl(value: string): string {
  const url = new URL(value);
  const allowed = new Set(["www.payfast.co.za", "sandbox.payfast.co.za"]);
  if (url.protocol !== "https:" || !allowed.has(url.hostname)) {
    throw new Error("Unexpected payment gateway URL.");
  }
  return url.toString();
}

export default async function CheckoutPage({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  await requireVerifiedStudent(`/checkout/${reference}`);
  const checkout = await studentApi<CheckoutPayload>(
    `/student/checkout/${encodeURIComponent(reference)}/`,
  );
  const gatewayUrl = assertPayFastUrl(checkout.gateway_url);

  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-2xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10"><span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><CreditCard className="size-7" /></span><p className="eyebrow mt-7">Secure checkout</p><h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">Continue to PayFast.</h1><p className="mt-4 text-base leading-7 text-[#60708a]">Amaris has created this checkout from the course price stored on the server. Your browser cannot change the amount or activate course access.</p><div className="mt-6 rounded-2xl bg-[#f6f8fc] p-5 text-sm text-[#52617a]"><p><strong>Reference:</strong> {checkout.reference}</p><p className="mt-2 flex items-center gap-2"><ShieldCheck className="size-4 text-[#147a4b]" /> Access activates only after PayFast verifies the payment callback.</p></div><form action={gatewayUrl} method="post" className="mt-8">{Object.entries(checkout.fields).map(([name,value]) => <input key={name} type="hidden" name={name} value={value} />)}<button type="submit" className="min-h-12 w-full rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white hover:bg-[#123d79]">Pay securely with PayFast</button></form><p className="mt-5 text-center text-xs leading-5 text-[#60708a]">Do not refresh after submitting to PayFast. If confirmation is delayed, your payment-status page will keep access locked until server verification succeeds.</p><Link href="/dashboard" className="mt-6 block text-center text-sm font-semibold text-[#1f5bbd]">Return to dashboard</Link></div></section><Footer /></main>;
}
