import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock3, FileText, RefreshCw, Video } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentLiveClassBooking } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Live Class Booking Confirmation",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

function formatClassTime(input: string): string {
  return new Intl.DateTimeFormat("en-ZA", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: "Africa/Johannesburg",
  }).format(new Date(input));
}

export default async function LiveClassConfirmationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const reference = value(params.reference).trim();
  await requireVerifiedStudent(
    reference
      ? `/book-online-live-class/confirmation?reference=${encodeURIComponent(reference)}`
      : "/book-online-live-class",
  );

  if (!reference) {
    return (
      <main className="min-h-screen bg-[#f5f7fb]">
        <Header />
        <section className="mx-auto max-w-2xl px-5 py-20 text-center">
          <h1 className="text-4xl font-semibold">Booking reference missing</h1>
          <Link href="/book-online-live-class" className="mt-6 inline-flex rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
            Return to booking
          </Link>
        </section>
        <Footer />
      </main>
    );
  }

  let booking: Awaited<ReturnType<typeof getStudentLiveClassBooking>> | null = null;
  try {
    booking = await getStudentLiveClassBooking(reference);
  } catch {
    booking = null;
  }

  const confirmed = booking?.status === "confirmed";

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          {confirmed ? (
            <CheckCircle2 className="size-14 text-[#13715f]" />
          ) : (
            <Clock3 className="size-14 text-[#b37a10]" />
          )}
          <p className="eyebrow mt-7">Live class booking</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">
            {confirmed ? "Your Zoom class is confirmed." : "Payment confirmation is being verified."}
          </h1>

          {!booking ? (
            <p className="mt-5 text-sm leading-7 text-[#60708a]">
              We could not retrieve this booking yet. If you have just returned from PayFast,
              wait a moment and refresh. Access is never granted from a browser redirect alone.
            </p>
          ) : (
            <>
              <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
                <div><dt className="font-semibold">Booking reference</dt><dd className="mt-1 font-mono text-[#60708a]">{booking.booking_reference}</dd></div>
                <div><dt className="font-semibold">Status</dt><dd className="mt-1 capitalize text-[#60708a]">{booking.status.replaceAll("_", " ")}</dd></div>
                <div><dt className="font-semibold">Tutor</dt><dd className="mt-1 text-[#60708a]">{booking.tutor}</dd></div>
                <div><dt className="font-semibold">Class</dt><dd className="mt-1 text-[#60708a]">{booking.programme} · {booking.subject} · {booking.level}</dd></div>
                <div><dt className="font-semibold">Topic</dt><dd className="mt-1 text-[#60708a]">{booking.topic}</dd></div>
                <div><dt className="font-semibold">Date and time</dt><dd className="mt-1 text-[#60708a]">{formatClassTime(booking.starts_at)}</dd></div>
                <div><dt className="font-semibold">Amount</dt><dd className="mt-1 text-[#60708a]">R{booking.amount}</dd></div>
                {booking.invoice_number && <div><dt className="font-semibold">Invoice</dt><dd className="mt-1 text-[#60708a]">{booking.invoice_number}</dd></div>}
              </dl>

              {confirmed && booking.zoom_join_url && (
                <a
                  href={booking.zoom_join_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"
                >
                  <Video className="size-4" /> Open Zoom class
                </a>
              )}

              {confirmed && (
                <div className="mt-5 grid gap-3 text-sm leading-7 text-[#60708a]">
                  <p className="flex items-start gap-2"><FileText className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />A confirmation email and invoice are queued for your registered email address.</p>
                  <p className="flex items-start gap-2"><Clock3 className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />A reminder is sent approximately 30 minutes before the class starts.</p>
                </div>
              )}
            </>
          )}

          {!confirmed && (
            <Link
              href={`/book-online-live-class/confirmation?reference=${encodeURIComponent(reference)}`}
              className="mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-[#b7c5d8] px-6 py-3 font-bold text-[#0b2a5b]"
            >
              <RefreshCw className="size-4" /> Refresh payment status
            </Link>
          )}
        </div>
      </section>
      <Footer />
    </main>
  );
}
