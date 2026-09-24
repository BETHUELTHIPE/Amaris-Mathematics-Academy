import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock3, FileText, RefreshCw } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentCustomVideoRequest } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Custom Video Request Confirmation",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

export default async function CustomVideoConfirmationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const reference = value(params.reference).trim();
  await requireVerifiedStudent(
    reference
      ? `/request-your-own-video/confirmation?reference=${encodeURIComponent(reference)}`
      : "/request-your-own-video",
  );

  if (!reference) {
    return (
      <main className="min-h-screen bg-[#f5f7fb]">
        <Header />
        <section className="mx-auto max-w-2xl px-5 py-20 text-center">
          <h1 className="text-4xl font-semibold">Request reference missing</h1>
          <Link href="/request-your-own-video" className="mt-6 inline-flex rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
            Return to custom video requests
          </Link>
        </section>
        <Footer />
      </main>
    );
  }

  let videoRequest: Awaited<ReturnType<typeof getStudentCustomVideoRequest>> | null = null;
  try {
    videoRequest = await getStudentCustomVideoRequest(reference);
  } catch {
    videoRequest = null;
  }

  const paid = Boolean(videoRequest && ["paid", "in_progress", "completed"].includes(videoRequest.status));

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          {paid ? <CheckCircle2 className="size-14 text-[#13715f]" /> : <Clock3 className="size-14 text-[#b37a10]" />}
          <p className="eyebrow mt-7">Custom video request</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">
            {paid ? "Your request and payment are confirmed." : "Payment confirmation is being verified."}
          </h1>

          {videoRequest && (
            <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
              <div><dt className="font-semibold">Reference</dt><dd className="mt-1 font-mono text-[#60708a]">{videoRequest.request_reference}</dd></div>
              <div><dt className="font-semibold">Status</dt><dd className="mt-1 capitalize text-[#60708a]">{videoRequest.status.replaceAll("_", " ")}</dd></div>
              <div><dt className="font-semibold">Curriculum</dt><dd className="mt-1 text-[#60708a]">{videoRequest.programme}</dd></div>
              <div><dt className="font-semibold">Subject</dt><dd className="mt-1 text-[#60708a]">{videoRequest.subject}</dd></div>
              <div><dt className="font-semibold">Grade / level</dt><dd className="mt-1 text-[#60708a]">{videoRequest.level}</dd></div>
              <div><dt className="font-semibold">Topic</dt><dd className="mt-1 text-[#60708a]">{videoRequest.topic}</dd></div>
              {videoRequest.amount && <div><dt className="font-semibold">Amount</dt><dd className="mt-1 text-[#60708a]">{videoRequest.currency} {videoRequest.amount}</dd></div>}
              {videoRequest.invoice_number && <div><dt className="font-semibold">Invoice</dt><dd className="mt-1 text-[#60708a]">{videoRequest.invoice_number}</dd></div>}
            </dl>
          )}

          {paid ? (
            <p className="mt-6 flex items-start gap-2 text-sm leading-7 text-[#60708a]">
              <FileText className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />
              Your invoice PDF and confirmation are queued for your registered email address, and the academy team is notified of the new request.
            </p>
          ) : (
            <Link
              href={`/request-your-own-video/confirmation?reference=${encodeURIComponent(reference)}`}
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
