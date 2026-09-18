import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock3, RefreshCw, XCircle } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Payment Status", robots: { index: false, follow: false } };

type PaymentStatus = {
  reference: string;
  state: "pending" | "processing" | "paid" | "cancelled" | "failed" | "expired" | "refunded";
  course_slug: string;
  course_title: string;
  amount: string;
  currency: string;
  gateway_verified: boolean;
  enrollment_active: boolean;
  invoice_number: string | null;
};

const copy = {
  pending: ["Payment pending", "PayFast has not yet verified this payment. Do not pay again."],
  processing: ["Payment verification in progress", "The callback reached Amaris but verification is being retried. Do not pay again."],
  paid: ["Payment verified", "Your course access is active."],
  cancelled: ["Payment cancelled", "No course access was activated."],
  failed: ["Payment failed", "No course access was activated. You can start a new checkout when ready."],
  expired: ["Checkout expired", "This pending checkout is outside the verification window. Start a new checkout."],
  refunded: ["Payment refunded", "This payment has been refunded. Contact support if you need help with access."],
} as const;

export default async function PaymentStatusPage({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = await params;
  await requireVerifiedStudent(`/payments/status/${reference}`);
  const payment = await studentApi<PaymentStatus>(
    `/student/payments/${encodeURIComponent(reference)}/`,
  );
  const [title, message] = copy[payment.state];
  const positive = payment.state === "paid";
  const Icon = positive ? CheckCircle2 : payment.state === "pending" || payment.state === "processing" ? Clock3 : XCircle;

  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="mx-auto max-w-2xl px-5 py-16 lg:px-8 lg:py-24"><div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 sm:p-10"><Icon className={`size-12 ${positive ? "text-[#147a4b]" : "text-[#b16a00]"}`} /><p className="eyebrow mt-6">Authoritative payment status</p><h1 className="mt-3 text-4xl font-semibold tracking-[-.04em]">{title}</h1><p className="mt-4 text-base leading-7 text-[#60708a]">{message}</p><dl className="mt-7 grid gap-3 rounded-2xl bg-[#f6f8fc] p-5 text-sm"><div><dt className="text-[#60708a]">Course</dt><dd className="font-semibold">{payment.course_title}</dd></div><div><dt className="text-[#60708a]">Reference</dt><dd className="font-mono">{payment.reference}</dd></div><div><dt className="text-[#60708a]">Amount</dt><dd className="font-semibold">{payment.currency} {payment.amount}</dd></div>{payment.invoice_number && <div><dt className="text-[#60708a]">Invoice</dt><dd className="font-semibold">{payment.invoice_number}</dd></div>}</dl>{positive && payment.enrollment_active ? <Link href="/dashboard" className="mt-8 block rounded-full bg-[#0b2a5b] px-6 py-3 text-center font-bold text-white">Continue learning</Link> : <form method="get" className="mt-8"><button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-[#b9c9df] px-6 py-3 font-bold text-[#0b2a5b]"><RefreshCw className="size-4" /> Refresh payment status</button></form>}</div></section><Footer /></main>;
}
