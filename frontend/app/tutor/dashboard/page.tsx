import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { BookOpen, CalendarDays, CheckCircle2, Clock3, LogOut, Plus, ShieldCheck, Video } from "lucide-react";
import { signOutAction } from "@/app/auth/actions";
import { Footer } from "@/components/site/footer";
import { Header } from "@/components/site/header";
import { createTutorSlotAction, pauseTutorSlotAction, updateTutorSlotAction } from "@/app/tutor/actions";
import { getTutorDashboard, getTutorEarnings, TutorApiError, type TutorEarnings, type TutorSlot } from "@/lib/tutor-api";
import { TutorEarningsPanel } from "@/components/site/tutor-earnings";
import { paginatePrivateRows, PrivatePagination } from "@/components/site/private-pagination";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Tutor Dashboard — Amaris Mathematics Academy", robots: { index: false, follow: false } };

const programmes = [["caps", "CAPS"], ["ieb", "IEB"], ["tvet", "TVET"], ["university", "University"]] as const;
const subjects = [["mathematics", "Mathematics"], ["mathematical_literacy", "Mathematical Literacy"]] as const;

const sessionFormatter = new Intl.DateTimeFormat("en-ZA", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg",
});
const formDateFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Africa/Johannesburg", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function formatSessionTime(value: string): string {
  return sessionFormatter.format(new Date(value));
}

function localDateTime(value: string): string {
  const parts = formDateFormatter.formatToParts(new Date(value));
  const part = (name: string) => parts.find((item) => item.type === name)?.value || "00";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function SlotFields({ slot }: { slot?: TutorSlot }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Programme
        <select name="programme" defaultValue={slot?.programme ?? "caps"} required className="min-h-12 rounded-xl border border-[#dce4ef] bg-white px-3 font-normal">
          {programmes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Subject
        <select name="subject" defaultValue={slot?.subject ?? "mathematics"} required className="min-h-12 rounded-xl border border-[#dce4ef] bg-white px-3 font-normal">
          {subjects.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Grade or level
        <input name="level" type="text" required minLength={2} maxLength={80} placeholder="Grade 12 / N3 / First year" defaultValue={slot?.level ?? ""} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Session start (South Africa time)
        <input name="starts_at" type="datetime-local" required defaultValue={slot ? localDateTime(slot.starts_at) : undefined} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Number of hours
        <input name="duration_hours" type="number" required min={1} max={24} step={1} defaultValue={slot?.duration_hours ?? 1} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
        <span className="text-xs font-normal text-[#60708a]">R250 per whole hour; the end time is calculated automatically.</span>
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Zoom meeting link
        <input name="zoom_join_url" type="url" required placeholder="https://..." defaultValue={slot?.zoom_join_url ?? ""} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
        <span className="text-xs font-normal text-[#60708a]">This link is kept private until a student&apos;s payment is confirmed.</span>
      </label>
      <label className="flex items-center gap-3 text-sm font-semibold text-[#263852] sm:col-span-2">
        <input type="checkbox" name="is_active" defaultChecked={slot?.is_active ?? true} className="size-5 accent-[#1f5bbd]" />
        Publish this slot for student booking
      </label>
    </div>
  );
}

function TutorEarningsSkeleton() {
  return <section id="earnings" aria-label="Loading your private earnings" role="status" className="min-h-72 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8">
    <div aria-hidden="true" className="space-y-5">
      <div className="h-6 w-52 max-w-full rounded bg-[#e9eef6]" />
      <div className="h-10 w-72 max-w-full rounded bg-[#e9eef6]" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => <div key={index} className="h-28 rounded-2xl bg-[#f1f5fb]" />)}
      </div>
    </div>
    <span className="sr-only">Loading verified private tutor earnings</span>
  </section>;
}

async function TutorEarningsDetails({ pending }: { pending: Promise<TutorEarnings | null> }) {
  return <TutorEarningsPanel earnings={await pending} />;
}

export default async function TutorDashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; success?: string; slots_page?: string; bookings_page?: string }>;
}) {
  const notices = await searchParams;
  // Start independently scoped financial read while loading the timetable.
  // Django still verifies tutor permissions on each no-store API request.
  const pendingEarnings = getTutorEarnings().catch((): TutorEarnings | null => null);
  let dashboard: Awaited<ReturnType<typeof getTutorDashboard>>;
  try {
    dashboard = await getTutorDashboard();
  } catch (error) {
    if (error instanceof TutorApiError && error.status === 401 && error.message.includes("Sign in")) {
      redirect("/tutor/login");
    }
    const denied = error instanceof TutorApiError && [401, 403].includes(error.status);
    return (
      <main className="min-h-screen bg-[#f5f7fb]">
        <Header />
        <section className="mx-auto max-w-2xl px-5 py-20">
          <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-9">
            <ShieldCheck className="size-10 text-[#1f5bbd]" />
            <h1 className="mt-5 text-3xl font-semibold">{denied ? "Tutor access requires approval" : "Tutor service unavailable"}</h1>
            <p className="mt-4 leading-7 text-[#60708a]">
              {denied
                ? "Your email must be verified and an academy administrator must approve your matching Django user in the Tutors group. Student login alone cannot grant tutor access."
                : "We could not reach your private tutor dashboard. Please try again shortly."}
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/tutor/login" className="rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">Tutor sign in</Link>
              <Link href="/contact" className="rounded-full border border-[#dce4ef] px-6 py-3 font-bold text-[#1f5bbd]">Contact academy</Link>
            </div>
          </div>
        </section>
        <Footer />
      </main>
    );
  }

  const slotHistory = paginatePrivateRows(dashboard.slots, notices.slots_page, 8);
  const bookingHistory = paginatePrivateRows(dashboard.bookings, notices.bookings_page, 8);

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="bg-[#07152d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-10 lg:px-8 lg:py-14">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-[#ffcc66]">Private tutor workspace</p>
          <div className="mt-3 flex flex-wrap items-start justify-between gap-5">
            <div>
              <h1 className="text-4xl font-semibold tracking-tight">Welcome, {dashboard.tutor.name}.</h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-white/70">Manage your Zoom class timetable, booking details and teaching hours from one secure dashboard.</p>
            </div>
            <form action={signOutAction}>
              <button type="submit" className="flex min-h-11 items-center gap-2 rounded-full border border-white/25 px-5 text-sm font-semibold hover:bg-white/10">
                <LogOut className="size-4" /> Sign out
              </button>
            </form>
          </div>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {[
              ["Published upcoming slots", String(dashboard.summary.upcoming_slots), CalendarDays],
              ["Confirmed classes", String(dashboard.summary.confirmed_classes), BookOpen],
              ["Lesson rate", `R${dashboard.rate_per_hour}/hour`, Clock3],
            ].map(([label, value, Icon]) => {
              const Graphic = Icon as typeof CalendarDays;
              return <div key={String(label)} className="rounded-2xl border border-white/15 bg-white/10 p-5"><Graphic className="size-5 text-[#ffcc66]" /><p className="mt-4 text-2xl font-bold">{String(value)}</p><p className="mt-1 text-sm text-white/65">{String(label)}</p></div>;
            })}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl space-y-8 px-5 py-10 lg:px-8 lg:py-14">
        <Suspense fallback={<TutorEarningsSkeleton />}><TutorEarningsDetails pending={pendingEarnings} /></Suspense>
        {notices.success && <div role="status" className="flex items-center gap-3 rounded-xl border border-[#a7ddcb] bg-[#ebfbf4] p-4 text-sm text-[#136950]"><CheckCircle2 className="size-5" />{notices.success.slice(0, 180)}</div>}
        {notices.error && <div role="alert" className="rounded-xl border border-[#f5c2bf] bg-[#fff3f3] p-4 text-sm text-[#9b2525]">{notices.error.slice(0, 180)}</div>}

        <section className="rounded-[2rem] border border-[#dce4ef] bg-white p-6 sm:p-9" aria-labelledby="new-tutor-slot">
          <div className="flex items-start gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-[#edf3ff] text-[#1f5bbd]"><Plus className="size-6" /></span>
            <div>
              <p className="eyebrow">Manage availability</p>
              <h2 id="new-tutor-slot" className="mt-2 text-2xl font-semibold">Offer a new live Zoom class</h2>
              <p className="mt-2 text-sm leading-7 text-[#60708a]">Choose your teaching hours and Zoom link. All times are South Africa Standard Time (SAST).</p>
            </div>
          </div>
          <form action={createTutorSlotAction} className="mt-7 grid gap-5">
            <SlotFields />
            <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-bold text-white hover:bg-[#123d79]">Publish tutor availability</button>
          </form>
        </section>

        <section id="slots-list" className="scroll-mt-28" aria-labelledby="my-slots">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div><p className="eyebrow">My timetable</p><h2 id="my-slots" className="mt-2 text-3xl font-semibold tracking-tight">Your teaching slots</h2></div>
            <Link href="/book-online-live-class" className="text-sm font-bold text-[#1f5bbd]">See public booking page →</Link>
          </div>
          {dashboard.slots.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-7 text-sm text-[#60708a]">No classes have been published yet. Use the form above to offer your first session.</div>
          ) : (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {slotHistory.rows.map((slot) => {
                const editable = slot.editable;
                return (
                  <article key={slot.id} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-6">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-[#1f5bbd]">{slot.programme.toUpperCase()} · {slot.level}</span>
                      <span className="rounded-full bg-[#f1f5fb] px-3 py-1 text-xs font-bold text-[#263852]">{slot.reserved ? "Reserved" : slot.is_active ? "Published" : "Paused"}</span>
                    </div>
                    <h3 className="mt-3 text-xl font-semibold">{slot.subject === "mathematics" ? "Mathematics" : "Mathematical Literacy"}</h3>
                    <p className="mt-3 flex items-center gap-2 text-sm text-[#60708a]"><CalendarDays className="size-4" />{formatSessionTime(slot.starts_at)}–{formatSessionTime(slot.ends_at)}</p>
                    <p className="mt-2 flex items-center gap-2 text-sm text-[#60708a]"><Clock3 className="size-4" />{slot.duration_hours} hour(s) · R{slot.price}</p>
                    {editable ? (
                      <div className="mt-5">
                        <details className="rounded-xl border border-[#dce4ef] p-4">
                          <summary className="cursor-pointer font-semibold text-[#1f5bbd]">Edit session details</summary>
                          <form action={updateTutorSlotAction} className="mt-5 grid gap-4">
                            <input type="hidden" name="slot_id" value={slot.id} />
                            <SlotFields slot={slot} />
                            <button type="submit" className="min-h-11 rounded-full bg-[#0b2a5b] px-5 font-semibold text-white">Save changes</button>
                          </form>
                        </details>
                        {slot.is_active && <form action={pauseTutorSlotAction} className="mt-3"><input type="hidden" name="slot_id" value={slot.id} /><button type="submit" className="text-sm font-semibold text-[#ae3232] underline underline-offset-4">Pause this unbooked slot</button></form>}
                      </div>
                    ) : <p className="mt-5 text-xs leading-6 text-[#60708a]">Reserved or past sessions cannot be changed online. Contact Amaris support for assistance.</p>}
                  </article>
                );
              })}
            </div>
          )}
          <PrivatePagination basePath="/tutor/dashboard" anchor="slots-list" queryKey="slots_page" current={slotHistory.current} totalPages={slotHistory.totalPages} preserve={{ bookings_page: bookingHistory.current }} />
        </section>

        <section id="bookings-list" className="scroll-mt-28" aria-labelledby="my-bookings">
          <p className="eyebrow">Private teaching schedule</p>
          <h2 id="my-bookings" className="mt-2 text-3xl font-semibold tracking-tight">Student bookings</h2>
          {dashboard.bookings.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-[#dce4ef] bg-white p-7 text-sm text-[#60708a]">Your paid and pending class bookings will appear here automatically.</div>
          ) : (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {bookingHistory.rows.map((booking) => (
                <article key={booking.reference} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div><p className="text-sm font-bold text-[#1f5bbd]">{booking.level} · {booking.topic}</p><h3 className="mt-2 text-xl font-semibold">{booking.duration_hours} hour Zoom lesson</h3></div>
                    <span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold capitalize text-[#1f5bbd]">{booking.status.replaceAll("_", " ")}</span>
                  </div>
                  <p className="mt-3 flex items-center gap-2 text-sm text-[#60708a]"><CalendarDays className="size-4" />{formatSessionTime(booking.starts_at)}</p>
                  <p className="mt-2 text-sm text-[#60708a]">Booking {booking.reference} · R{booking.amount}</p>
                  {booking.student_email && <p className="mt-3 text-sm text-[#263852]">Student: {booking.student_name} · {booking.student_email}</p>}
                  {booking.zoom_join_url && (
                    <a href={booking.zoom_join_url} target="_blank" rel="noopener noreferrer" className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 text-sm font-bold text-white">
                      <Video className="size-4" /> Open Zoom class
                    </a>
                  )}
                  {!booking.student_email && <p className="mt-3 text-xs text-[#60708a]">Student details and Zoom access are shown after verified payment.</p>}
                </article>
              ))}
            </div>
          )}
          <PrivatePagination basePath="/tutor/dashboard" anchor="bookings-list" queryKey="bookings_page" current={bookingHistory.current} totalPages={bookingHistory.totalPages} preserve={{ slots_page: slotHistory.current }} />
        </section>
      </div>
      <Footer />
    </main>
  );
}
