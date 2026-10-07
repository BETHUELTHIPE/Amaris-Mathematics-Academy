import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Clock3, FileText, PlayCircle, RefreshCw } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentVideoRequest } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Video Request Confirmation",
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
  const params = await searchParams;
  const reference = value(params.reference).trim();
  await requireVerifiedStudent(
    reference
      ? `/request-video/confirmation?reference=${encodeURIComponent(reference)}`
      : "/request-video",
  );

  if (!reference) {
    return (
      <main className="min-h-screen bg-[#f5f7fb]">
        <Header />
        <section className="mx-auto max-w-2xl px-5 py-20 text-center">
          <h1 className="text-4xl font-semibold">Request reference missing</h1>
          <Link href="/request-video" className="mt-6 inline-flex rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
            Return to video request
          </Link>
        </section>
        <Footer />
      </main>
    );
  }

  let videoRequest: Awaited<ReturnType<typeof getStudentVideoRequest>> | null = null;
  try {
    videoRequest = await getStudentVideoRequest(reference);
  } catch {
    videoRequest = null;
  }

  const paid = videoRequest?.status === "paid" || videoRequest?.status === "fulfilled";
  const fulfilled = videoRequest?.status === "fulfilled";
  const video = videoRequest?.video ?? null;

  let heading = "Payment confirmation is being verified.";
  if (fulfilled) heading = "Your custom video is ready.";
  else if (paid) heading = "Payment confirmed — your video is being prepared.";

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-2xl px-5 py-14 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          {paid ? (
            <CheckCircle2 className="size-14 text-[#13715f]" />
          ) : (
            <Clock3 className="size-14 text-[#b37a10]" />
          )}
          <p className="eyebrow mt-7">Custom video request</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em]">{heading}</h1>

          {!videoRequest ? (
            <p className="mt-5 text-sm leading-7 text-[#60708a]">
              We could not retrieve this request yet. If you have just returned from PayFast,
              wait a moment and refresh. Access is never granted from a browser redirect alone.
            </p>
          ) : (
            <>
              <dl className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
                <div><dt className="font-semibold">Request reference</dt><dd className="mt-1 font-mono text-[#60708a]">{videoRequest.request_reference}</dd></div>
                <div><dt className="font-semibold">Status</dt><dd className="mt-1 capitalize text-[#60708a]">{videoRequest.status.replaceAll("_", " ")}</dd></div>
                <div><dt className="font-semibold">Programme</dt><dd className="mt-1 text-[#60708a]">{videoRequest.programme} · {videoRequest.subject}</dd></div>
                <div><dt className="font-semibold">Grade / level</dt><dd className="mt-1 text-[#60708a]">{videoRequest.level}</dd></div>
                <div><dt className="font-semibold">Topic</dt><dd className="mt-1 text-[#60708a]">{videoRequest.topic}</dd></div>
                {videoRequest.details && (
                  <div><dt className="font-semibold">Details</dt><dd className="mt-1 whitespace-pre-wrap text-[#60708a]">{videoRequest.details}</dd></div>
                )}
                <div><dt className="font-semibold">Amount</dt><dd className="mt-1 text-[#60708a]">R{videoRequest.amount}</dd></div>
                {videoRequest.invoice_number && <div><dt className="font-semibold">Invoice</dt><dd className="mt-1 text-[#60708a]">{videoRequest.invoice_number}</dd></div>}
              </dl>

              {fulfilled && video?.provider === "youtube" && video.youtube_video_id && (
                <div className="mt-6">
                  <h2 className="text-lg font-semibold text-[#0b2a5b]">{video.title}</h2>
                  <div className="mt-3 aspect-video overflow-hidden rounded-2xl bg-black">
                    <iframe
                      title={video.title}
                      className="h-full w-full"
                      src={`https://www.youtube-nocookie.com/embed/${video.youtube_video_id}`}
                      allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                </div>
              )}
              {fulfilled && video?.provider === "vimeo" && video.vimeo_video_id && (
                <div className="mt-6">
                  <h2 className="text-lg font-semibold text-[#0b2a5b]">{video.title}</h2>
                  <div className="mt-3 aspect-video overflow-hidden rounded-2xl bg-black">
                    <iframe
                      title={video.title}
                      className="h-full w-full"
                      src={`https://player.vimeo.com/video/${video.vimeo_video_id}${video.vimeo_hash ? `?h=${video.vimeo_hash}` : ""}`}
                      allow="autoplay; fullscreen; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                </div>
              )}

              {paid && (
                <div className="mt-5 grid gap-3 text-sm leading-7 text-[#60708a]">
                  {fulfilled ? (
                    <p className="flex items-start gap-2"><PlayCircle className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />Your bespoke video is ready above — stream it any time from this page.</p>
                  ) : (
                    <p className="flex items-start gap-2"><Clock3 className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />A tutor is preparing your custom video. You will be emailed as soon as it is ready, and it will appear on this page.</p>
                  )}
                  <p className="flex items-start gap-2"><FileText className="mt-1 size-4 shrink-0 text-[#1f5bbd]" />A confirmation email and invoice are queued for your registered email address.</p>
                </div>
              )}
            </>
          )}

          {!fulfilled && (
            <Link
              href={`/request-video/confirmation?reference=${encodeURIComponent(reference)}`}
              className="mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-[#b7c5d8] px-6 py-3 font-bold text-[#0b2a5b]"
            >
              <RefreshCw className="size-4" /> Refresh request status
            </Link>
          )}
        </div>
      </section>
      <Footer />
    </main>
  );
}
