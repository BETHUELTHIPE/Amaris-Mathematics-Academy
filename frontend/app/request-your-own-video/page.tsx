import type { Metadata } from "next";
import { CreditCard, FileUp, ListChecks, Video } from "lucide-react";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { getVideoRequestOptions } from "@/lib/video-requests";

export const metadata: Metadata = {
  title: "Request Your Own Video",
  description: "Request a custom mathematics video from Amaris Mathematics Academy.",
};

export default async function RequestYourOwnVideoPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const options = await getVideoRequestOptions();
  const params = await searchParams;
  const requestError = Boolean(params.error);

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <p className="eyebrow">Request Your Own Video</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-.045em] sm:text-5xl">
            Send your topic and source material, then continue to secure payment.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[#60708a]">
            Choose the curriculum and subject, tell us the exact grade or level and topic,
            upload your supporting documents, and pay only the administrator-configured fee.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Custom video request process">
          {[
            ["1", "Choose curriculum", "CAPS, IEB, TVET or University"],
            ["2", "Choose subject & topic", "Mathematics or Mathematical Literacy"],
            ["3", "Upload source files", "Multiple validated supporting documents"],
            ["4", "Pay & receive invoice", "PayFast verification, emailed invoice and team notification"],
          ].map(([number, title, detail]) => (
            <li key={number} className="rounded-2xl border border-[#dce4ef] bg-white p-5">
              <span className="grid size-9 place-items-center rounded-full bg-[#0b2a5b] text-sm font-bold text-white">
                {number}
              </span>
              <h2 className="mt-4 font-semibold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-[#60708a]">{detail}</p>
            </li>
          ))}
        </ol>

        {requestError && (
          <div role="alert" className="mt-7 rounded-2xl border border-[#efb0b0] bg-[#fff2f2] p-5 text-sm text-[#8b2525]">
            We could not create that request. Check the fields and uploaded file types, then try again.
          </div>
        )}

        <form
          action="/api/video-requests"
          method="post"
          encType="multipart/form-data"
          className="mt-8 grid gap-7 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8"
        >
          <fieldset className="grid gap-5 lg:grid-cols-2">
            <legend className="mb-4 flex items-center gap-2 text-xl font-semibold">
              <ListChecks className="size-5 text-[#1f5bbd]" /> 1–2. Curriculum, subject and topic
            </legend>

            <label className="grid gap-2 text-sm font-semibold">
              Curriculum
              <select name="programme" required className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
                <option value="">Choose curriculum</option>
                {options.programmes.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>

            <label className="grid gap-2 text-sm font-semibold">
              Subject
              <select name="subject" required className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
                <option value="">Choose subject</option>
                {options.subjects.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>

            <label className="grid gap-2 text-sm font-semibold">
              Grade / level
              <input
                name="level"
                required
                minLength={2}
                maxLength={80}
                list="school-levels"
                placeholder="Grade 10, Grade 11, Grade 12, or your TVET/University level"
                className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
              />
              <datalist id="school-levels">
                {options.school_levels.map((item) => <option key={item} value={item} />)}
              </datalist>
            </label>

            <label className="grid gap-2 text-sm font-semibold">
              Topic
              <input
                name="topic"
                required
                minLength={2}
                maxLength={180}
                placeholder="Enter the exact topic from your source material"
                className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
              />
            </label>

            <p className="lg:col-span-2 rounded-xl bg-[#f7f9fc] p-4 text-sm leading-6 text-[#60708a]">
              {options.topic_notice}
            </p>
          </fieldset>

          <fieldset className="grid gap-4 border-t border-[#e4eaf2] pt-7">
            <legend className="mb-4 flex items-center gap-2 text-xl font-semibold">
              <FileUp className="size-5 text-[#1f5bbd]" /> 3. Upload supporting files
            </legend>
            <label className="grid gap-2 text-sm font-semibold">
              Supporting documents
              <input
                type="file"
                name="files"
                multiple
                required
                accept=".pdf,.jpg,.jpeg,.png,.heic,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.odt"
                className="rounded-xl border border-dashed border-[#9fb2cb] bg-[#f7f9fc] p-5 font-normal"
              />
            </label>
            <p className="text-sm leading-6 text-[#60708a]">
              Up to {options.max_files} files, maximum {options.max_file_size_mb} MB each.
              The server validates the type, size and file signature before storing the upload.
            </p>
          </fieldset>

          <section className="border-t border-[#e4eaf2] pt-7" aria-labelledby="payment-step">
            <div className="flex items-start gap-3">
              <CreditCard className="mt-1 size-5 shrink-0 text-[#1f5bbd]" />
              <div>
                <h2 id="payment-step" className="text-xl font-semibold">4. Continue to payment</h2>
                {options.checkout_enabled && options.price ? (
                  <p className="mt-2 text-sm leading-6 text-[#60708a]">
                    Admin-configured fee: <strong>{options.currency} {options.price}</strong>.
                    The final amount is set again by the server before the signed PayFast checkout.
                  </p>
                ) : (
                  <p className="mt-2 rounded-xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm leading-6 text-[#765314]">
                    Custom-video pricing has not been configured by an administrator yet. No price has been invented or hardcoded.
                  </p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={!options.checkout_enabled}
              className="mt-6 inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white disabled:cursor-not-allowed disabled:bg-[#9aa8b9]"
            >
              <Video className="size-4" /> Create request and continue to payment
            </button>
          </section>
        </form>
      </section>
      <Footer />
    </main>
  );
}
