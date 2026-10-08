import type { Metadata } from "next";
import { Clock3, LockKeyhole, Mail, Video } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { VideoRequestForm } from "@/components/site/video-request-form";
import { requireVerifiedStudent } from "@/lib/auth";
import { getVideoRequestPackages } from "@/lib/video-requests";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Request a Video",
  description: "Request a personalised mathematics lesson video from Amaris Mathematics Academy.",
};

export default async function RequestVideoPage() {
  await requireVerifiedStudent("/request-a-video");
  const packages = await getVideoRequestPackages();
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <p className="eyebrow">Request a personalised lesson video</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-.045em] sm:text-5xl">Send the exact mathematics work you want explained.</h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[#60708a]">Payment is verified before your permanent ticket enters the tutor queue. Your documents, queue status, invoice and completed video remain linked to your student account.</p>
        </div>
      </section>
      <section className="mx-auto grid max-w-7xl gap-8 px-5 py-10 lg:grid-cols-[minmax(0,1fr)_340px] lg:px-8 lg:py-14">
        <VideoRequestForm packages={packages} />
        <aside className="grid h-fit gap-4">
          {[
            [LockKeyhole, "Private by design", "Supporting documents are stored in the private student bucket and are never listed publicly."],
            [Clock3, "Paid FIFO queue", "Your position is calculated from server-verified payment time. Estimates are ranges, not guarantees."],
            [Mail, "Progress notifications", "You receive updates when queued, next, recording and ready."],
            [Video, "Student-only playback", "Completed YouTube or direct videos are released only through your authenticated dashboard."],
          ].map(([Icon, title, detail]) => {
            const ItemIcon = Icon as typeof Video;
            return <div key={title as string} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><ItemIcon className="size-6 text-[#1f5bbd]" /><h2 className="mt-4 font-semibold">{title as string}</h2><p className="mt-2 text-sm leading-6 text-[#60708a]">{detail as string}</p></div>;
          })}
        </aside>
      </section>
      <Footer />
    </main>
  );
}

