import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CreditCard,
  FileVideo,
  Mail,
  Sparkles,
} from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getVideoRequestInfo } from "@/lib/video-requests";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Request a Custom Maths Video",
  description:
    "Request a bespoke Amaris Mathematics Academy video on the exact topic you need. A tutor records and delivers it after verified payment.",
};

function queryValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function RequestVideoPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [params, info] = await Promise.all([searchParams, getVideoRequestInfo()]);

  const programmes = info.programmes;
  const subjects = info.subjects;

  const programme = queryValue(params.programme);
  const subject = queryValue(params.subject);
  const level = queryValue(params.level);
  const topic = queryValue(params.topic).slice(0, 180);
  const details = queryValue(params.details).slice(0, 2000);

  const validProgramme = programmes.some(({ value }) => value === programme)
    ? programme
    : "";
  const validSubject = subjects.some(({ value }) => value === subject)
    ? subject
    : "";

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <p className="eyebrow">Request a video · made to order</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-.045em] sm:text-5xl">
            Ask for a custom maths video on exactly your topic.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[#60708a]">
            Tell us the programme, grade and topic you are stuck on. A tutor records a
            bespoke video just for you for <strong>R{info.price}</strong>. Your request is
            queued only after PayFast verifies the payment, and you are emailed as soon as the
            video is ready.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Request process">
          {[
            ["1", "Describe your video", "Programme, subject, grade/level and topic"],
            ["2", "Pay securely", `R${info.price} via PayFast, server-priced`],
            ["3", "Tutor records it", "A tutor prepares a bespoke video for your request"],
            ["4", "Watch & keep", "You are emailed and can stream it from your confirmation page"],
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

        <form
          method="get"
          action="/request-video/checkout"
          className="mt-8 grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:grid-cols-2"
        >
          <label className="grid gap-2 text-sm font-semibold">
            Programme
            <select
              name="programme"
              required
              defaultValue={validProgramme}
              disabled={programmes.length === 0}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal disabled:bg-[#f1f4f8]"
            >
              <option value="">
                {programmes.length ? "Choose programme" : "Programmes unavailable"}
              </option>
              {programmes.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-2 text-sm font-semibold">
            Subject
            <select
              name="subject"
              required
              defaultValue={validSubject}
              disabled={subjects.length === 0}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal disabled:bg-[#f1f4f8]"
            >
              <option value="">
                {subjects.length ? "Choose subject" : "Subjects unavailable"}
              </option>
              {subjects.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-2 text-sm font-semibold">
            Grade / level
            <input
              name="level"
              required
              minLength={1}
              maxLength={80}
              defaultValue={level}
              placeholder="e.g. Grade 12"
              className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
            />
          </label>

          <label className="grid gap-2 text-sm font-semibold">
            Topic
            <input
              name="topic"
              required
              minLength={2}
              maxLength={180}
              defaultValue={topic}
              placeholder="e.g. Calculus — the chain rule"
              className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
            />
          </label>

          <label className="grid gap-2 text-sm font-semibold lg:col-span-2">
            What should the video cover? (optional)
            <textarea
              name="details"
              maxLength={2000}
              rows={4}
              defaultValue={details}
              placeholder="Add any specific questions, worked examples or past-paper references you would like the tutor to include."
              className="rounded-xl border border-[#c9d5e5] px-4 py-3 font-normal"
            />
          </label>

          <div className="lg:col-span-2">
            <button
              type="submit"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white"
            >
              Continue to secure payment <ArrowRight className="size-4" />
            </button>
            <p className="mt-3 text-sm text-[#60708a]">
              You will be asked to sign in as a verified student before payment.
            </p>
          </div>
        </form>

        <section className="mt-10 grid gap-4 md:grid-cols-3">
          {[
            [CreditCard, "Secure payment", `The server fixes the price at R${info.price} and PayFast must verify the payment.`],
            [Sparkles, "Made for you", "A tutor records a bespoke video that answers your exact request."],
            [Mail, "Delivered by email", "You are emailed the moment your video is ready to watch."],
          ].map(([Icon, title, detail]) => {
            const C = Icon as typeof CreditCard;
            return (
              <div key={title as string} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                <C className="size-6 text-[#1f5bbd]" />
                <h2 className="mt-4 font-semibold">{title as string}</h2>
                <p className="mt-2 text-sm leading-6 text-[#60708a]">{detail as string}</p>
              </div>
            );
          })}
        </section>

        <div className="mt-8 flex flex-wrap items-center gap-3 rounded-2xl border border-[#dce4ef] bg-white p-6 text-sm text-[#60708a]">
          <FileVideo className="size-5 shrink-0 text-[#1f5bbd]" />
          <span>
            Prefer a live lesson instead?{" "}
            <Link href="/book-online-live-class" className="font-semibold text-[#1f5bbd]">
              Book an online live class
            </Link>
            .
          </span>
          <CheckCircle2 className="ml-auto hidden size-5 text-[#13715f] sm:block" />
        </div>
      </section>
      <Footer />
    </main>
  );
}
