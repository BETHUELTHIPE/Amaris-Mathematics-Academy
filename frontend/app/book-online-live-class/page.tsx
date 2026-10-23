import { CUSTOM_CHOICE, isSchoolProgramme } from "@/lib/school-curriculum.mjs";
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
import { getGradeLevels, programmes, subjects } from "@/lib/booking-grade-levels.mjs";
import { LiveClassBookingFilters } from "./live-class-booking-filters";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Book Online Live Class",
  description:
    "Book a flexible-length Amaris Mathematics Academy Zoom class with an available tutor.",
};

function queryValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function inPreferredTime(startsAt: string, preference: string): boolean {
  if (preference === "any") return true;
  const hour = Number(new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit", hourCycle: "h23", timeZone: "Africa/Johannesburg",
  }).format(new Date(startsAt)));
  if (preference === "morning") return hour >= 5 && hour < 12;
  if (preference === "afternoon") return hour >= 12 && hour < 17;
  if (preference === "evening") return hour >= 17 && hour < 22;
  return hour >= 22 || hour < 5;
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
  const level = queryValue(params.level) === CUSTOM_CHOICE ? queryValue(params.customLevel).trim().slice(0, 80) : queryValue(params.level);
  const topic = (queryValue(params.topic) === CUSTOM_CHOICE ? queryValue(params.customTopic) : queryValue(params.topic)).trim().slice(0, 180);
  const tutorId = queryValue(params.tutor).trim();
  const requestedTime = queryValue(params.time);
  const timePreference = ["morning", "afternoon", "evening", "overnight"].includes(requestedTime) ? requestedTime : "any";

  const validProgramme = programmes.some(([value]) => value === programme)
    ? programme
    : "";
  const validSubject = subjects.some(([value]) => value === subject)
    ? subject
    : "";

  const availability =
    validProgramme && validSubject
      ? await getLiveClassSlots({
          programme: validProgramme,
          subject: validSubject,
        })
      : { slots: [], unavailable: false };
  const availableSlots = availability.slots;

  const levels = getGradeLevels(
    validProgramme,
    availableSlots.map((slot) => slot.level),
    validSubject,
  );
  // Never treat a stale or cross-programme grade as a valid selection.
  const chosenLevel = levels.includes(level) || (validProgramme && !isSchoolProgramme(validProgramme) && level.length > 0 && level.length <= 80) ? level : "";
  const levelSlots = chosenLevel
    ? availableSlots.filter((slot) => slot.level === chosenLevel)
    : availableSlots;
  const tutors = Array.from(
    new Map(levelSlots.map((slot) => [slot.tutor_id, slot.tutor] as const)),
    ([id, name]) => ({ id, name }),
  ).sort((a, b) => a.name.localeCompare(b.name));
  const selectedTutorId = tutors.some((tutor) => String(tutor.id) === tutorId) ? tutorId : "";
  const matchingSlots = chosenLevel
    ? levelSlots.filter((slot) =>
        (!selectedTutorId || String(slot.tutor_id) === selectedTutorId)
        && inPreferredTime(slot.starts_at, timePreference),
      )
    : [];

  const readyForSlot = Boolean(
    validProgramme && validSubject && chosenLevel && topic.length >= 2,
  );

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
            Our online booking desk is open <strong>24 hours a day, seven days a week</strong>.
            Choose any tutor with an available slot, including early mornings, evenings and overnight.
            CAPS and IEB Mathematics cover Grades 7–12. Sessions cost <strong>R250 per hour</strong>,
            and your place is confirmed only after PayFast verifies payment.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Booking process">
          {[
            ["1", "Choose programme", "CAPS, IEB, TVET or University"],
            ["2", "Choose subject", "Mathematics or Mathematical Literacy"],
            ["3", "Choose level, topic & tutor", "Find your ideal morning, daytime or overnight slot"],
            ["4", "Pay & receive your class details", "Student, tutor and admin notifications after verified payment"],
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

        <div className="mt-8 rounded-2xl border border-[#bfd6ff] bg-[#edf3ff] p-5 text-sm leading-7 text-[#0b2a5b]">
          <strong>Learning never closes at Amaris.</strong> Select your preferred tutor and a time that fits your life,
          whether you work during the day or at night. Times are shown in South African Standard Time (SAST).
          A slot is bookable only while that tutor is actually available.
        </div>
        <LiveClassBookingFilters
          initialProgramme={validProgramme}
          initialSubject={validSubject}
          initialLevel={chosenLevel}
          initialTopic={topic}
          initialTutorId={selectedTutorId}
          initialTimePreference={timePreference}
          tutors={tutors}
          offeredLevels={availableSlots.map((slot) => slot.level)}
        />

        <section className="mt-8" aria-labelledby="available-slots">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="eyebrow">Tutor timetable</p>
              <h2 id="available-slots" className="mt-2 text-3xl font-semibold tracking-[-.035em]">
                Available Zoom slots
              </h2>
            </div>
            <span className="text-sm font-semibold text-[#1f5bbd]">R250 per booked hour</span>
          </div>

          {!readyForSlot ? (
            <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-6 text-sm leading-7 text-[#60708a]">
              Complete the programme, subject, grade/level and topic fields above to choose a tutor slot.
            </div>
          ) : availability.unavailable ? (
            <div className="mt-5 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-sm leading-7 text-[#765314]">
              Tutor availability is temporarily unavailable. Please try again later before making a payment.
            </div>
          ) : matchingSlots.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-sm leading-7 text-[#765314]">
              No tutor slot matches these choices just now. Try “Any available tutor” or “Any time”, or check back when new daytime and overnight slots are published.
            </div>
          ) : (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {matchingSlots.map((slot) => {
                const checkoutUrl =
                  `/book-online-live-class/checkout?slot=${encodeURIComponent(String(slot.id))}&topic=${encodeURIComponent(topic)}&attempt=${crypto.randomUUID()}`;
                return (
                  <article key={slot.id} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-[#1f5bbd]">{slot.tutor}</p>
                        {slot.id === matchingSlots[0]?.id && <p className="mt-1 text-xs font-semibold text-[#13715f]">Earliest matching class</p>}
                        <h3 className="mt-2 text-xl font-semibold">{slot.level} · {slot.subject_label}</h3>
                      </div>
                      <span className="rounded-full bg-[#daf5ec] px-3 py-1 text-xs font-bold text-[#13715f]">
                        Available
                      </span>
                    </div>
                    <dl className="mt-5 grid gap-3 text-sm text-[#60708a]">
                      <div className="flex items-start gap-3">
                        <CalendarDays className="mt-0.5 size-4 shrink-0 text-[#1f5bbd]" />
                        <div><dt className="sr-only">Date and time</dt><dd>{formatClassTime(slot.starts_at)} SAST</dd></div>
                      </div>
                      <div className="flex items-start gap-3">
                        <Clock3 className="mt-0.5 size-4 shrink-0 text-[#1f5bbd]" />
                        <div><dt className="sr-only">Duration</dt><dd>{slot.duration_minutes / 60} hour(s) · R{slot.price} total</dd></div>
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
            [CreditCard, "Secure payment", "The server calculates R250 per selected hour; PayFast must verify the total."],
            [Mail, "Everyone is informed", "After verified payment, you receive your invoice and Zoom details; your tutor and the Django admin team receive the full booking details."],
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
