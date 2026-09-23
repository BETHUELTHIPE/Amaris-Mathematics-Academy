import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  CreditCard,
  Mail,
  Video,
} from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getLiveClassSlots } from "@/lib/live-classes";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Book Online Live Class",
  description:
    "Book a one-hour Amaris Mathematics Academy Zoom class with an available tutor.",
};

const programmes = [
  ["caps", "CAPS"],
  ["ieb", "IEB"],
  ["tvet", "TVET"],
  ["university", "University"],
] as const;

const subjects = [
  ["mathematics", "Mathematics"],
  ["mathematical_literacy", "Mathematical Literacy"],
] as const;

function queryValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function formatClassTime(value: string): string {
  return new Intl.DateTimeFormat("en-ZA", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: "Africa/Johannesburg",
  }).format(new Date(value));
}

export default async function BookOnlineLiveClassPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const programme = queryValue(params.programme);
  const subject = queryValue(params.subject);
  const level = queryValue(params.level);
  const topic = queryValue(params.topic).trim().slice(0, 180);

  const validProgramme = programmes.some(([value]) => value === programme)
    ? programme
    : "";
  const validSubject = subjects.some(([value]) => value === subject)
    ? subject
    : "";

  const availableSlots =
    validProgramme && validSubject
      ? await getLiveClassSlots({
          programme: validProgramme,
          subject: validSubject,
        })
      : [];

  const levels = [...new Set(availableSlots.map((slot) => slot.level))].sort(
    (left, right) => left.localeCompare(right, "en-ZA", { numeric: true }),
  );
  const matchingSlots = level
    ? availableSlots.filter((slot) => slot.level === level)
    : [];

  const readyForSlot = Boolean(validProgramme && validSubject && level && topic.length >= 2);

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
          <p className="eyebrow">Book online live class · Zoom</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-.045em] sm:text-5xl">
            Choose your programme, topic and tutor time.
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[#60708a]">
            Each live Zoom class is one hour and costs <strong>R250</strong>.
            Your booking is confirmed only after PayFast verifies the payment.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Booking process">
          {[
            ["1", "Choose programme", "CAPS, IEB, TVET or University"],
            ["2", "Choose subject", "Mathematics or Mathematical Literacy"],
            ["3", "Choose level & topic", "Then select an available tutor time"],
            ["4", "Pay & receive Zoom details", "R250, confirmation, invoice and 30-minute reminder"],
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
          className="mt-8 grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:grid-cols-2"
        >
          <label className="grid gap-2 text-sm font-semibold">
            Programme
            <select
              name="programme"
              required
              defaultValue={validProgramme}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
            >
              <option value="">Choose programme</option>
              {programmes.map(([value, label]) => (
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
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
            >
              <option value="">Choose subject</option>
              {subjects.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-2 text-sm font-semibold">
            Grade / level
            <select
              name="level"
              required
              defaultValue={level}
              disabled={!validProgramme || !validSubject || levels.length === 0}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal disabled:bg-[#f1f4f8]"
            >
              <option value="">
                {validProgramme && validSubject
                  ? levels.length
                    ? "Choose available grade / level"
                    : "No tutor levels available yet"
                  : "Choose programme and subject first"}
              </option>
              {levels.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>

          <label className="grid gap-2 text-sm font-semibold">
            Topic
            <input
              name="topic"
              required
              minLength={2}
              maxLength={180}
              defaultValue={topic}
              placeholder="e.g. Grade 12 Calculus — differentiation"
              className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
            />
          </label>

          <div className="lg:col-span-2">
            <button
              type="submit"
              className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white"
            >
              Show available tutor times
            </button>
          </div>
        </form>

        <section className="mt-8" aria-labelledby="available-slots">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="eyebrow">Tutor timetable</p>
              <h2 id="available-slots" className="mt-2 text-3xl font-semibold tracking-[-.035em]">
                Available Zoom slots
              </h2>
            </div>
            <span className="text-sm font-semibold text-[#1f5bbd]">R250 per one-hour session</span>
          </div>

          {!readyForSlot ? (
            <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-6 text-sm leading-7 text-[#60708a]">
              Complete the programme, subject, grade/level and topic fields above to choose a tutor slot.
            </div>
          ) : matchingSlots.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-sm leading-7 text-[#765314]">
              No open tutor slot currently matches this selection. Choose another grade/level or check again later.
            </div>
          ) : (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {matchingSlots.map((slot) => {
                const checkoutUrl =
                  `/book-online-live-class/checkout?slot=${encodeURIComponent(slot.id)}&topic=${encodeURIComponent(topic)}`;
                return (
                  <article key={slot.id} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-[#1f5bbd]">{slot.tutor}</p>
                        <h3 className="mt-2 text-xl font-semibold">{slot.level} · {slot.subject_label}</h3>
                      </div>
                      <span className="rounded-full bg-[#daf5ec] px-3 py-1 text-xs font-bold text-[#13715f]">
                        Available
                      </span>
                    </div>
                    <dl className="mt-5 grid gap-3 text-sm text-[#60708a]">
                      <div className="flex items-start gap-3">
                        <CalendarDays className="mt-0.5 size-4 shrink-0 text-[#1f5bbd]" />
                        <div><dt className="sr-only">Date and time</dt><dd>{formatClassTime(slot.starts_at)}</dd></div>
                      </div>
                      <div className="flex items-start gap-3">
                        <Clock3 className="mt-0.5 size-4 shrink-0 text-[#1f5bbd]" />
                        <div><dt className="sr-only">Duration</dt><dd>{slot.duration_minutes} minutes</dd></div>
                      </div>
                      <div className="flex items-start gap-3">
                        <Video className="mt-0.5 size-4 shrink-0 text-[#1f5bbd]" />
                        <div><dt className="sr-only">Delivery</dt><dd>Zoom link is released after verified payment.</dd></div>
                      </div>
                    </dl>
                    <Link
                      href={checkoutUrl}
                      className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"
                    >
                      Choose this slot <ArrowRight className="size-4" />
                    </Link>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <section className="mt-10 grid gap-4 md:grid-cols-3">
          {[
            [CreditCard, "Secure payment", "The server fixes the price at R250 and PayFast must verify the payment."],
            [Mail, "Confirmation & invoice", "A confirmation email with your class details and invoice is sent after verification."],
            [CheckCircle2, "30-minute reminder", "A scheduled reminder includes your tutor, start time and Zoom link."],
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
      </section>
      <Footer />
    </main>
  );
}
