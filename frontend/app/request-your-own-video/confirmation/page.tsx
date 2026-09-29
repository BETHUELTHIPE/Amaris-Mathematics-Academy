import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { CheckCircle2, Clock3, FileDown, RefreshCw, XCircle } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentCustomVideoRequest } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Custom Video Request Status",
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
  if (!reference) redirect("/request-your-own-video");

  await requireVerifiedStudent(
    `/request-your-own-video/confirmation?reference=${encodeURIComponent(reference)}`,
  );

  let requestRecord;
  try {
    requestRecord = await getStudentCustomVideoRequest(reference);
  } catch {
    redirect("/request-your-own-video?error=request-unavailable");
  }

  const paid = ["paid", "in_progress", "delivered"].includes(requestRecord.status);
  const cancelled = requestRecord.status === "cancelled";

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          {paid ? (
            <CheckCircle2 className="size-14 text-[#13715f]" />
          ) : cancelled ? (
            <XCircle className="size-14 text-[#9b3030]" />
          ) : (
            <Clock3 className="size-14 text-[#8a6000]" />
          )}

          <p className="eyebrow mt-7">Step 5 · Request status</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">
            {paid
              ? "Payment verified"
              : cancelled
                ? "Payment not completed"
                : "Waiting for payment verification"}
          </h1>

          <p className="mt-5 text-base leading-8 text-[#60708a]">
            {paid
              ? "Your custom video request is recorded and queued for the Amaris team. A PDF invoice is generated and sent to your registered email by the notification worker."
              : cancelled
                ? "This request was not paid. You can start a new custom video request when you are ready."
                : "A browser return page is not proof of payment. Amaris waits for the server-verified PayFast notification before issuing an invoice."}
          </p>

          <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
            <div>
              <dt className="font-semibold text-[#263852]">Request reference</dt>
              <dd className="mt-1 font-mono text-[#60708a]">
                {requestRecord.request_reference}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-[#263852]">Topic</dt>
              <dd className="mt-1 text-[#60708a]">{requestRecord.topic}</dd>
            </div>
            <div>
              <dt className="font-semibold text-[#263852]">Status</dt>
              <dd className="mt-1 capitalize text-[#60708a]">
                {requestRecord.status.replaceAll("_", " ")}
              </dd>
            </div>
            {requestRecord.invoice_number && (
              <div>
                <dt className="font-semibold text-[#263852]">Invoice</dt>
                <dd className="mt-1 text-[#60708a]">
                  {requestRecord.invoice_number}
                </dd>
              </div>
            )}
          </dl>

          <div className="mt-7 flex flex-wrap gap-3">
            {!paid && !cancelled && (
              <Link
                href={`/request-your-own-video/confirmation?reference=${encodeURIComponent(reference)}`}
                className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"
              >
                <RefreshCw className="size-4" /> Refresh status
              </Link>
            )}
            {requestRecord.invoice_pdf_url && (
              <a
                href={requestRecord.invoice_pdf_url}
                className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#c9d5e5] px-6 py-3 font-bold text-[#0b2a5b]"
              >
                <FileDown className="size-4" /> Open invoice PDF
              </a>
            )}
            <Link
              href="/dashboard"
              className="inline-flex min-h-12 items-center rounded-full border border-[#c9d5e5] px-6 py-3 font-bold text-[#0b2a5b]"
            >
              Student dashboard
            </Link>
          </div>
        </div>
      </section>
      <Footer />
    </main>
  );
}
