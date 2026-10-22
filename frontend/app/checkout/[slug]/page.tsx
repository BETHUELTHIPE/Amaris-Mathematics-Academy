import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, CreditCard, ShieldCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { createStudentCheckout } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata = { title: "Secure Checkout", robots: { index: false, follow: false } };

export default async function CheckoutPage({ params }: { params: Promise<{ slug: string }> }) {
  await requireVerifiedStudent("/dashboard");
  const { slug } = await params;

  let checkout: Awaited<ReturnType<typeof createStudentCheckout>>;
  try {
    checkout = await createStudentCheckout(slug);
  } catch {
    redirect("/payments/failed?reason=checkout-unavailable");
  }

  const sandbox = checkout.gateway_url.includes("sandbox.payfast.co.za");

  return <main className="min-h-screen min-w-0 bg-[#f5f7fb]"><Header />
    <section className="mx-auto max-w-2xl min-w-0 px-4 py-8 sm:px-5 sm:py-16 lg:px-8 lg:py-24">
      <Link href={`/courses/${slug}`} className="inline-flex min-h-11 items-center gap-2 rounded-lg text-sm font-semibold text-[#1f5bbd] hover:underline"><ArrowLeft className="size-4" />Back to course</Link>
      <div className="mt-5 min-w-0 rounded-[2rem] border border-[#dce4ef] bg-white p-5 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:mt-8 sm:p-10">
        <span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><CreditCard className="size-7" /></span>
        <p className="eyebrow mt-7">Secure checkout</p>
        <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-[-.045em] [overflow-wrap:anywhere] sm:text-4xl">{checkout.course.title}</h1>
        <p className="mt-4 text-sm leading-7 text-[#60708a]">Payment reference <span className="break-all font-mono font-semibold text-[#263852]">{checkout.payment_reference}</span>. Access is activated only after the server verifies the PayFast notification.</p>
        {sandbox && <div className="mt-5 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm text-[#765314]">Sandbox mode is active. No real money is charged.</div>}
        <form method="post" action={checkout.gateway_url} className="mt-7">
          {Object.entries(checkout.fields).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}
          <button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
            Continue to PayFast
          </button>
        </form>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-center text-xs text-[#60708a]"><ShieldCheck className="size-4" />Server-priced · signed checkout · verified callback required</div>
      </div>
    </section><Footer /></main>;
}
