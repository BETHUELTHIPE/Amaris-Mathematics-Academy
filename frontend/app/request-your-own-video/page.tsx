import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CustomVideoRequestWizard } from "@/components/site/custom-video-request-wizard";
import { requireVerifiedStudent } from "@/lib/auth";
import { getCustomVideoOptions } from "@/lib/custom-videos";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Request Your Own Video",
  description:
    "Request a custom Amaris Mathematics Academy teaching video using your curriculum, subject, grade, topic and supporting files.",
};

export default async function RequestYourOwnVideoPage() {
  await requireVerifiedStudent("/request-your-own-video");
  const options = await getCustomVideoOptions();
  const available = options.enabled && options.pricing_configured;

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <p className="eyebrow">Request your own teaching video</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-.045em] sm:text-5xl">
            Send the exact mathematics topic you want explained.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[#60708a]">
            Choose your curriculum, subject and grade, upload the material we should
            use, then pay the academy-configured fee securely through PayFast.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
        {!available ? (
          <div
            role="status"
            className="rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-sm leading-7 text-[#765314]"
          >
            Custom-video requests are not open for payment yet. The academy must
            configure and enable the flat fee before this service can accept requests.
            No price has been invented or hardcoded.
          </div>
        ) : (
          <CustomVideoRequestWizard options={options} />
        )}
      </section>
      <Footer />
    </main>
  );
}
