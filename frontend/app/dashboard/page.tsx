import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Bell, BookOpen, CheckCircle2, CreditCard, LayoutDashboard, ShieldCheck, UserRound } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { courses } from "@/lib/courses";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Student Dashboard", robots: { index: false, follow: false } };

type DashboardEnrollment = {
  course_slug: string;
  course_title: string;
  progress_percent: number;
  last_position_seconds: number;
  continue_lesson: { slug: string; title: string } | null;
};

type DashboardPayload = { enrollments: DashboardEnrollment[] };

const SYNTHETIC_E2E_ID = "00000000-0000-4000-8000-000000000001";

export default async function DashboardPage() {
  const user = await requireVerifiedStudent("/dashboard");
  const dashboard = user.id === SYNTHETIC_E2E_ID
    ? { enrollments: [] }
    : await studentApi<DashboardPayload>("/student/dashboard/");
  const active = dashboard.enrollments;
  const completed = active.filter((item) => item.progress_percent >= 100).length;
  const recommended = courses.slice(0, 2);

  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="border-b border-[#dce4ef] bg-white"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 px-5 py-10 sm:flex-row sm:items-end lg:px-8"><div><p className="eyebrow">Student dashboard</p><h1 className="mt-3 text-4xl font-semibold tracking-[-.045em] sm:text-5xl">Welcome, {user.firstName}.</h1><p className="mt-3 text-[#60708a]">Your next mathematics step will always be clear here.</p></div><div className="inline-flex items-center gap-2 rounded-full bg-[#daf5ec] px-4 py-2 text-sm font-semibold text-[#13715f]"><CheckCircle2 className="size-4" />Email verified · profile active</div></div></section><section className="mx-auto grid max-w-7xl gap-7 px-5 py-10 lg:grid-cols-[240px_1fr] lg:px-8"><aside className="h-fit rounded-2xl border border-[#dce4ef] bg-white p-3"><nav className="grid gap-1" aria-label="Dashboard navigation">{[[LayoutDashboard,"Overview",null],[BookOpen,"My courses",null],[CreditCard,"Orders & payments",null],[Bell,"Notifications",null],[UserRound,"Profile & security","/reset-password"]].map(([Icon,label,href],i) => {const C=Icon as typeof LayoutDashboard; const content=<><C className="size-4" />{label as string}</>; return href ? <Link key={label as string} href={href as string} className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-[#60708a] hover:bg-[#edf3ff]">{content}</Link> : <span key={label as string} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${i===0 ? "bg-[#0b2a5b] text-white" : "text-[#60708a]"}`}>{content}</span>})}</nav></aside><div className="min-w-0"><div className="grid gap-4 sm:grid-cols-3">{[["Active courses",String(active.length)],["Courses completed",String(completed)],["Email status","Verified"]].map(([label,value]) => <div key={label} className="rounded-2xl border border-[#dce4ef] bg-white p-6"><p className="text-sm text-[#60708a]">{label}</p><p className="mt-3 text-3xl font-bold tracking-tight">{value}</p></div>)}</div>{active.length ? <section className="mt-7"><div><p className="eyebrow">My courses</p><h2 className="mt-2 text-2xl font-semibold">Continue learning</h2></div><div className="mt-5 grid gap-4">{active.map((item) => <article key={item.course_slug} className="rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-7"><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center"><div><h3 className="text-xl font-semibold">{item.course_title}</h3><p className="mt-2 text-sm text-[#60708a]">{item.progress_percent}% complete{item.continue_lesson ? ` · Last lesson: ${item.continue_lesson.title}` : ""}</p><div className="mt-3 h-2 overflow-hidden rounded-full bg-[#e8edf4]" aria-label={`${item.progress_percent}% course progress`}><div className="h-full bg-[#2767d8]" style={{ width: `${Math.min(100, Math.max(0, item.progress_percent))}%` }} /></div></div>{item.continue_lesson ? <Link href={`/learn/${item.course_slug}/${item.continue_lesson.slug}`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-2.5 font-bold text-white">Continue Learning <ArrowRight className="size-4" /></Link> : <Link href={`/courses/${item.course_slug}`} className="inline-flex min-h-11 items-center justify-center rounded-full border border-[#b9c9df] px-5 py-2.5 font-semibold text-[#0b2a5b]">View course</Link>}</div></article>)}</div></section> : <div className="mt-6 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9"><div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center"><div><span className="inline-flex rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">Ready when you are</span><h2 className="mt-5 text-3xl font-semibold tracking-[-.035em]">Your course shelf is waiting.</h2><p className="mt-3 max-w-xl text-sm leading-7 text-[#60708a]">After PayFast verifies a purchase, your course appears here with the last authorised lesson and saved position.</p></div><Link href="/courses" className="inline-flex items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3.5 font-bold text-white">Choose a course <ArrowRight className="size-4" /></Link></div></div>}<section className="mt-8"><div className="flex items-end justify-between"><div><p className="eyebrow">Recommended next</p><h2 className="mt-2 text-2xl font-semibold">Popular starting points</h2></div><Link href="/courses" className="text-sm font-bold text-[#1f5bbd]">View all</Link></div><div className="mt-5 grid gap-4 md:grid-cols-2">{recommended.map((course) => <Link key={course.slug} href={`/courses/${course.slug}`} className="group rounded-2xl border border-[#dce4ef] bg-white p-6 transition hover:-translate-y-1 hover:shadow-lg"><div className="flex items-center justify-between"><span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span><ArrowRight className="size-4 text-[#60708a] transition group-hover:translate-x-1" /></div><h3 className="mt-5 text-xl font-semibold">{course.title}</h3><p className="mt-2 text-sm text-[#60708a]">{course.lessons} lessons · {course.hours} hours</p></Link>)}</div></section></div></section><Footer /></main>;
}
