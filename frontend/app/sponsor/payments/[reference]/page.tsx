import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ShieldCheck, Wallet } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { getSponsorPayment, validSponsorGatewayUrl, type SponsorPaymentStatus } from "@/lib/sponsor-api";
import { checkSponsorPayment } from "@/app/sponsor/payment-actions";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Sponsor Payment", robots: { index: false, follow: false } };

export default async function SponsorPaymentPage({ params }: { params: Promise<{ reference: string }> }) {
  await requireVerifiedStudent("/sponsor");
  const { reference } = await params;
  if (!/^SC-[a-f0-9]{32}$/.test(reference)) notFound();
  let payment: SponsorPaymentStatus | null = null;
  try { payment = await getSponsorPayment(reference); } catch { /* Private service failure is shown without exposing records. */ }
  const verified = payment?.status === "received" && payment.gateway_verified;
  const provider = payment?.provider === "paystack" ? "Paystack" : "PayFast";
  const checkout = payment?.checkout && validSponsorGatewayUrl(payment.provider, payment.checkout.gateway_url) ? payment.checkout : null;
  return <main className="min-h-screen bg-[#f5f7fb] px-5 py-10 sm:py-20"><div className="mx-auto max-w-xl">
    <Link href="/sponsor?view=contributions" className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[#31537e]"><ArrowLeft size={16} />Back to sponsor dashboard</Link>
    <section className="mt-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-10">
      <Wallet size={32} className="text-[#236755]" aria-hidden="true" />
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">{!payment ? "Payment status unavailable" : verified ? payment.mode === "test" ? "Test payment verified" : "Thank you for your contribution" : payment.status === "refunded" ? "Refund recorded" : payment.status === "failed" ? "Payment not completed" : "Your sponsorship payment"}</h1>
      {payment ? <><p className="mt-4 text-2xl font-semibold">{new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR" }).format(Number(payment.amount))}</p><p className="mt-2 text-sm text-[#60708a]">{provider} · Reference <span className="break-all font-mono">{payment.reference}</span></p>
        {payment.mode === "test" && <p className="mt-5 rounded-xl bg-[#fff5de] p-4 text-sm text-[#795919]">Test mode. This transaction does not add to real sponsorship funding.</p>}
        <p className="mt-5 text-sm leading-7 text-[#60708a]">{verified ? "The gateway has verified this payment. Its status is recorded in your contribution history." : "A return from the payment page does not confirm payment. Your contribution is recorded as received only after gateway verification. If you have already paid, check the status before starting another payment."}</p>
        {checkout && payment.status === "pending" && (payment.provider === "payfast" ? <form method="post" action={checkout.gateway_url} className="mt-6">{Object.entries(checkout.fields).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}<button className="min-h-12 w-full rounded-xl bg-[#153d46] px-5 py-3 font-semibold text-white" type="submit">Continue to PayFast</button></form> : <a href={checkout.gateway_url} className="mt-6 flex min-h-12 items-center justify-center rounded-xl bg-[#153d46] px-5 py-3 font-semibold text-white">Continue to Paystack</a>)}
        {!verified && payment.provider === "paystack" && payment.status !== "refunded" && <form action={checkSponsorPayment.bind(null, reference)}><button type="submit" className="mt-4 min-h-12 w-full rounded-xl border border-[#ccd9df] px-5 py-3 font-semibold text-[#31537e]">Check payment status</button></form>}
        {!verified && <Link href={`/sponsor/payments/${encodeURIComponent(reference)}`} className="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-[#31537e]">Refresh recorded status</Link>}
      </> : <p className="mt-5 text-sm leading-7 text-[#60708a]">We could not load this payment. Return to your contributions and try again shortly.</p>}
      <p className="mt-7 flex items-center gap-2 text-xs text-[#60708a]"><ShieldCheck size={16} />Your card and banking details are entered on the gateway’s secure page.</p>
    </section>
  </div></main>;
}
