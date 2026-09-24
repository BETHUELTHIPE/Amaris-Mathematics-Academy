import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, CreditCard, FileText, ShieldCheck } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { requireVerifiedStudent } from "@/lib/auth";
import { createStudentCustomVideoCheckout } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Custom Video Checkout",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

export default async function CustomVideoCheckoutPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const reference = value(params.reference).trim();
  if (!reference) redirect("/request-your-own-video");

  await requireVerifiedStudent(
    `/request-your-own-video/checkout?reference=${encodeURIComponent(reference)}`,
  );

  let checkout: Awaited<ReturnType<typeof createStudentCustomVideoCheckout>>;
  try {
    checkout = await createStudentCustomVideoCheckout(reference);
  } catch {
    redirect("/request-your-own-video?error=checkout");
  }

  const sandbox = checkout.gateway_url.includes("sandbox.payfast.co.za");

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <Link href="/request-your-own-video" className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f5bbd]">
          <ArrowLeft className="size-4" /> Back to request
        </Link>

        <div className="mt-7 rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          <FileText className="size-12 text-[#1f5bbd]" />
          <p className="eyebrow mt-7">Custom video request</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">Confirm your payment</h1>

          <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
            <div><dt className="font-semibold">Request reference</dt><dd className="mt-1 font-mono text-[#60708a]">{checkout.request_reference}</dd></div>
            <div><dt className="font-semibold">Amount</dt><dd className="mt-1 text-lg font-bold text-[#0b2a5b]">{checkout.currency} {checkout.amount}</dd></div>
          </dl>

          <p className="mt-5 text-sm leading-7 text-[#60708a]">
            The amount shown here is the administrator-configured server price. Your request is marked paid only after the server verifies the PayFast notification.
          </p>

          {sandbox && (
            <div className="mt-5 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm text-[#765314]">
              Sandbox mode is active. No real money is charged.
            </div>
          )}

          <form method="post" action={checkout.gateway_url} className="mt-7">
            {Object.entries(checkout.fields).map(([name, fieldValue]) => (
              <input key={name} type="hidden" name={name} value={fieldValue} />
            ))}
            <button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
              <CreditCard className="size-4" /> Pay with PayFast
            </button>
          </form>

          <div className="mt-5 flex items-center justify-center gap-2 text-center text-xs text-[#60708a]">
            <ShieldCheck className="size-4 shrink-0" />
            Server-priced · signed checkout · verified callback required
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
