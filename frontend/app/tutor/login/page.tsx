import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { GraduationCap, ShieldCheck, CalendarDays, Clock3 } from "lucide-react";
import { tutorLoginAction } from "@/app/tutor/actions";
import { GoogleAuthButton } from "@/components/site/google-auth-button";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getStudentIdentity } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Tutor Portal Login — Amaris Mathematics Academy" };

export default async function TutorLoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const params = await searchParams;
  const identity = await getStudentIdentity();
  if (identity?.emailVerified) redirect("/tutor/dashboard");

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto grid max-w-6xl gap-8 px-5 py-12 lg:grid-cols-[1fr_1.05fr] lg:items-center lg:gap-16 lg:px-8 lg:py-20">
        <div className="rounded-[2rem] bg-[#07152d] p-8 text-white lg:p-11">
          <span className="grid size-14 place-items-center rounded-2xl bg-[#ffcc66] text-[#07152d]">
            <GraduationCap className="size-7" />
          </span>
          <p className="mt-8 text-xs font-bold uppercase tracking-[.2em] text-[#ffcc66]">Amaris tutor workspace</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight lg:text-5xl">Teach on your own timetable.</h1>
          <p className="mt-5 max-w-lg text-base leading-8 text-white/70">
            Create Zoom availability, choose the number of teaching hours, manage your bookings, and prepare for upcoming classes.
          </p>
          <div className="mt-8 grid gap-4 text-sm text-white/80">
            <div className="flex items-center gap-3"><CalendarDays className="size-5 text-[#ffcc66]" /> Manage your teaching schedule</div>
            <div className="flex items-center gap-3"><Clock3 className="size-5 text-[#ffcc66]" /> Offer 1–24 whole-hour classes at R250/hour</div>
            <div className="flex items-center gap-3"><ShieldCheck className="size-5 text-[#ffcc66]" /> Private, verified tutor-only access</div>
          </div>
        </div>
        <div className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.1)] sm:p-10">
          <p className="eyebrow">Tutor sign in</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">Welcome, tutor.</h2>
          <p className="mt-3 text-sm leading-7 text-[#60708a]">
            <Link href="/tutor/apply" className="font-semibold text-[#1f5bbd] underline">Apply to become a tutor</Link> if you have not yet been approved. Use your verified Amaris account. Your academy administrator must first assign you to the Tutors permission group.
          </p>
          <div className="mt-6"><GoogleAuthButton label="Continue with Google" next="/tutor/dashboard" /></div>
          <div className="my-6 flex items-center gap-3 text-xs font-bold uppercase tracking-wider text-[#60708a]"><span className="h-px flex-1 bg-[#dce4ef]" />or use email<span className="h-px flex-1 bg-[#dce4ef]" /></div>
          {params.error && <div role="alert" className="mb-5 rounded-xl border border-[#f5c2bf] bg-[#fff3f3] p-3 text-sm text-[#9b2525]">{params.error === "credentials" ? "The email or password is incorrect. Please try again." : "Authentication is unavailable. Please try again."}</div>}
          <form action={tutorLoginAction} className="grid gap-4">
            <input type="hidden" name="next" value="/tutor/dashboard" />
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              Email address
              <input required name="email" type="email" autoComplete="email" className="h-12 rounded-xl border border-[#dce4ef] px-4 font-normal" />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              Password
              <input required name="password" type="password" autoComplete="current-password" className="h-12 rounded-xl border border-[#dce4ef] px-4 font-normal" />
            </label>
            <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-bold text-white hover:bg-[#123d79]">Sign in to tutor dashboard</button>
          </form>
          <p className="mt-6 text-sm text-[#60708a]">
            <Link href="/forgot-password" className="font-semibold text-[#1f5bbd]">Forgot password?</Link>
            <span className="mx-2">·</span>
            <Link href="/book-online-live-class" className="font-semibold text-[#1f5bbd]">Student booking page</Link>
          </p>
        </div>
      </section>
      <Footer />
    </main>
  );
}
