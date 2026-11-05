import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock3, FileText, RefreshCw, Video } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentVideoRequest } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Video Request Status",
  robots: { index: false, follow: false },
};

function value(input: string | string[] | undefined): string {
  return Array.isArray(input) ? input[0] ?? "" : input ?? "";
}

export default async function VideoRequestConfirmationPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const reference = value((await searchParams).reference).trim();
  await requireVerifiedStudent(
    reference
      ? `/request-a-video/confirmation?reference=${encodeURIComponent(reference)}`
      : "/request-a-video",
  );
  let item: Awaited<ReturnType<typeof getStudentVideoRequest>> | null = null;
  if (reference) {
    try {
      item = await getStudentVideoRequest(reference);
    } catch {
      item = null;
    }
  }
  const paid = Boolean(item?.ticket_number);
  const ready = item?.status === "ready" && item.video;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-3xl px-5 py-14 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          {paid ? <CheckCircle2 className="size-14 text-[#13715f]" /> : <Clock3 className="size-14 text-[#b37a10]" />}
          <p className="eyebrow mt-7">Requested video</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">
            {ready ? "Your requested video is ready." : paid ? "Your paid request is being prepared." : "Payment confirmation is being verified."}
          </h1>

          {!item ? (
            <p className="mt-5 text-sm leading-7 text-[#60708a]">We could not retrieve this request yet. If you have just returned from PayFast, wait a moment and refresh. A browser redirect alone never places a request in the paid queue.</p>
          ) : (
            <>
              <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm sm:grid-cols-2">
                <div><dt className="font-semibold">Reference</dt><dd className="mt-1 break-all font-mono text-[#60708a]">{item.request_reference}</dd></div>
                <div><dt className="font-semibold">Ticket</dt><dd className="mt-1 font-mono text-[#60708a]">{item.ticket_number ?? "Issued after verification"}</dd></div>
                <div><dt className="font-semibold">Status</dt><dd className="mt-1 text-[#60708a]">{item.status_label}</dd></div>
                <div><dt className="font-semibold">Package</dt><dd className="mt-1 text-[#60708a]">{item.request_type_label}</dd></div>
                <div><dt className="font-semibold">Topic</dt><dd className="mt-1 text-[#60708a]">{item.topic}</dd></div>
                <div><dt className="font-semibold">Tutor</dt><dd className="mt-1 text-[#60708a]">{item.tutor}</dd></div>
                <div><dt className="font-semibold">Queue</dt><dd className="mt-1 text-[#60708a]">{item.queue_position ? `Position ${item.queue_position} · ${item.requests_ahead} ahead` : "Not in the active queue"}</dd></div>
                <div><dt className="font-semibold">Estimated window</dt><dd className="mt-1 text-[#60708a]">{item.estimated_ready_from && item.estimated_ready_to ? `${item.estimated_ready_from} to ${item.estimated_ready_to}` : "Updated as work progresses"}</dd></div>
              </dl>

              {ready && item.video?.provider === "youtube" && item.video.youtube_video_id && (
                <div className="mt-7 overflow-hidden rounded-2xl bg-black">
                  <iframe
                    className="aspect-video w-full"
                    src={`https://www.youtube-nocookie.com/embed/${item.video.youtube_video_id}?rel=0`}
                    title={`Requested lesson: ${item.topic}`}
                    allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                    referrerPolicy="strict-origin-when-cross-origin"
                  />
                </div>
              )}
              {ready && item.video?.provider === "direct" && (
                <video className="mt-7 aspect-video w-full rounded-2xl bg-black" controls controlsList="nodownload" preload="metadata">
                  <source src={`/request-a-video/video?reference=${encodeURIComponent(reference)}`} type="video/mp4" />
                </video>
              )}

              {item.invoice_ready && item.invoice_number && (
                <a href={`/request-a-video/invoice?reference=${encodeURIComponent(reference)}`} className="mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-[#b7c5d8] px-6 py-3 font-bold text-[#0b2a5b]">
                  <FileText className="size-4" /> Download invoice PDF
                </a>
              )}
            </>
          )}

          {!ready && reference && (
            <Link href={`/request-a-video/confirmation?reference=${encodeURIComponent(reference)}`} className="mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
              <RefreshCw className="size-4" /> Refresh request status
            </Link>
          )}
          <Link href="/request-a-video" className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-full px-5 font-semibold text-[#1f5bbd]">
            <Video className="size-4" /> Request another video
          </Link>
        </div>
      </section>
      <Footer />
    </main>
  );
}

