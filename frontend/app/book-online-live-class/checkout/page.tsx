import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, ShieldCheck, Video } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getVerifiedStudentBookingName } from "@/lib/registered-booking-name";
import { createStudentLiveClassCheckout, supportsPaystackLiveClassCheckout } from "@/lib/student-api";
import { PayFastHostedCheckout } from "@/components/site/payfast-hosted-checkout";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Live Class Checkout",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

function safePaystackCheckoutUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.origin === "https://checkout.paystack.com" && !url.username && !url.password && url.pathname.length > 1) {
      return url.href;
    }
  } catch {
    // Invalid or missing gateway URLs cannot open a hosted payment.
  }
  return null;
}

function formatClassTime(input: string): string {
  return new Intl.DateTimeFormat("en-ZA", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: "Africa/Johannesburg",
  }).format(new Date(input));
}

export default async function LiveClassCheckoutPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const slotId = value(params.slot).trim();
  const topic = value(params.topic).trim().slice(0, 180);
  const attempt = value(params.attempt).trim();
  const provider = value(params.provider);
  if (!slotId || topic.length < 2 || !/^[0-9a-f-]{36}$/i.test(attempt)) redirect("/book-online-live-class");

  const returnTo =
    `/book-online-live-class/checkout?slot=${encodeURIComponent(slotId)}&topic=${encodeURIComponent(topic)}&attempt=${encodeURIComponent(attempt)}`;
  if (provider && provider !== "payfast" && provider !== "paystack") redirect("/book-online-live-class");
  const student = await requireVerifiedStudent(provider ? `${returnTo}&provider=${provider}` : returnTo);
  const registeredName = await getVerifiedStudentBookingName(student.id);
  if (!registeredName) redirect("/account/complete-profile");

  if (!provider && await supportsPaystackLiveClassCheckout()) {
    return (
      <main className="min-h-screen bg-[#f5f7fb]">
        <Header />
        <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8">
          <div className="rounded-3xl border border-[#dce4ef] bg-white p-7 shadow-sm">
            <h1 className="text-3xl font-semibold text-[#07152d]">Choose how to pay</h1>
            <p className="mt-4 text-sm leading-6 text-[#526781]">Review your tutor slot and total after choosing a payment method.</p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <Link href={`${returnTo}&provider=payfast`} prefetch={false} className="grid min-h-12 place-items-center rounded-full bg-[#0b2a5b] px-5 py-3 font-bold text-white">
                PayFast
              </Link>
              <Link href={`${returnTo}&provider=paystack`} prefetch={false} className="grid min-h-12 place-items-center rounded-full border border-[#0b2a5b] px-5 py-3 font-bold text-[#0b2a5b]">
                Paystack
              </Link>
            </div>
          </div>
        </section>
        <Footer />
      </main>
    );
  }

  const paymentProvider = provider === "paystack" ? "paystack" : "payfast";
  let checkout: Awaited<ReturnType<typeof createStudentLiveClassCheckout>>;
  try {
    checkout = await createStudentLiveClassCheckout(slotId, topic, attempt, paymentProvider);
  } catch {
    redirect("/book-online-live-class?booking=unavailable");
  }

  if ((checkout.payment_provider ?? "payfast") !== paymentProvider) {
    redirect("/book-online-live-class?booking=unavailable");
  }
  const paystackUrl = paymentProvider === "paystack" ? safePaystackCheckoutUrl(checkout.gateway_url) : null;
  if (paymentProvider === "paystack" && !paystackUrl) redirect("/book-online-live-class?booking=unavailable");
  const sandbox = checkout.test_mode ?? checkout.gateway_url.includes("sandbox.payfast.co.za");
  const booking = checkout.booking;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <Link
          href="/book-online-live-class"
          className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f5bbd]"
        >
          <ArrowLeft className="size-4" /> Back to tutor timetable
        </Link>

        <div className="mt-7 rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          <span className="grid size-14 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]">
            <Video className="size-7" />
          </span>
          <p className="eyebrow mt-7">Zoom live class</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">Confirm your tutor slot</h1>

          <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm [overflow-wrap:anywhere]">
            <div>
              <dt className="font-semibold text-[#263852]">Registered student</dt>
              <dd className="mt-1 break-words text-[#60708a]">{registeredName.fullName}</dd>
            </div>
            <div><dt className="font-semibold text-[#263852]">Tutor</dt><dd className="mt-1 text-[#60708a]">{booking.tutor}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Class</dt><dd className="mt-1 text-[#60708a]">{booking.programme} · {booking.subject} · {booking.level}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Topic</dt><dd className="mt-1 text-[#60708a]">{booking.topic}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Date and time</dt><dd className="mt-1 text-[#60708a]">{formatClassTime(booking.starts_at)}</dd></div>
            <div><dt className="font-semibold text-[#263852]">Duration</dt><dd className="mt-1 text-[#60708a]">{booking.duration_minutes / 60} hour(s)</dd></div>
            <div><dt className="font-semibold text-[#263852]">Price</dt><dd className="mt-1 text-lg font-bold text-[#0b2a5b]">R{booking.amount} total (R250/hour)</dd></div>
          </dl>

          <p className="mt-5 text-sm leading-7 text-[#60708a] [overflow-wrap:anywhere]">
            Booking reference <span className="font-mono font-semibold text-[#263852]">{checkout.booking_reference}</span>.
            Your Zoom link is released only after the server verifies your payment.
          </p>

          {sandbox && (
            <div className="mt-5 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm text-[#765314]">
              Sandbox mode is active. No real money is charged.
            </div>
          )}

          {paystackUrl ? (
            <a href={paystackUrl} rel="noreferrer" className="mt-6 flex min-h-12 w-full items-center justify-center rounded-xl bg-[#0b2a5b] px-5 py-3 font-bold text-white">
              Pay R{booking.amount} with Paystack
            </a>
          ) : (
            <PayFastHostedCheckout checkout={checkout} buttonLabel={`Pay R${booking.amount} with PayFast`} />
          )}

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
