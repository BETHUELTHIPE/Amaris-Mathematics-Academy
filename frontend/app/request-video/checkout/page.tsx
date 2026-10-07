import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, CreditCard, ShieldCheck, Sparkles } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { createStudentVideoRequestCheckout } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Video Request Checkout",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

export default async function VideoRequestCheckoutPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const programme = value(params.programme).trim();
  const subject = value(params.subject).trim();
  const level = value(params.level).trim().slice(0, 80);
  const topic = value(params.topic).trim().slice(0, 180);
  const details = value(params.details).trim().slice(0, 2000);

  if (!programme || !subject || level.length < 1 || topic.length < 2) {
    redirect("/request-video");
  }

  const query = new URLSearchParams({ programme, subject, level, topic });
  if (details) query.set("details", details);
  const returnTo = `/request-video/checkout?${query.toString()}`;
  await requireVerifiedStudent(returnTo);

  let checkout: Awaited<ReturnType<typeof createStudentVideoRequestCheckout>>;
  try {
    checkout = await createStudentVideoRequestCheckout({
      programme,
      subject,
      level,
      topic,
      details,
    });
  } catch {
    redirect("/request-video?request=unavailable");
  }

  const sandbox = checkout.gateway_url.includes("sandbox.payfast.co.za");
  const request = checkout.request;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <Link
          href="/request-video"
          className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f5bbd]"
        >
          <ArrowLeft className="size-4" /> Back to video request
        </Link>

        <div className="mt-7 rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          <span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]">
            <Sparkles className="size-7" />
          </span>
          <p className="eyebrow mt-7">Custom maths video</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">Confirm your video request</h1>

          <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
            <div><dt className="font-semibold text-[#263852]">Programme</dt><dd className="mt-1 text-[#60708a]">{request.programme} · {request.subject}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Grade / level</dt><dd className="mt-1 text-[#60708a]">{request.level}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Topic</dt><dd className="mt-1 text-[#60708a]">{request.topic}</dd></div>
            {request.details && (
              <div><dt className="font-semibold text-[#263852]">Details</dt><dd className="mt-1 whitespace-pre-wrap text-[#60708a]">{request.details}</dd></div>
            )}
            <div><dt className="font-semibold text-[#263852]">Price</dt><dd className="mt-1 text-lg font-bold text-[#0b2a5b]">R{request.amount} for one custom video</dd></div>
          </dl>

          <p className="mt-5 text-sm leading-7 text-[#60708a]">
            Request reference <span className="font-mono font-semibold text-[#263852]">{checkout.request_reference}</span>.
            Your request is queued for a tutor only after the server verifies the PayFast notification.
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
            <button
              type="submit"
              className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"
            >
              <CreditCard className="size-4" /> Pay R{request.amount} with PayFast
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
