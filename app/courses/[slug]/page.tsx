import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Clock3, ShieldCheck } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { courses, formatRand, getCourse } from "@/lib/courses";
import { getStudentIdentity } from "@/lib/auth";

export const dynamic = "force-dynamic";

export function generateStaticParams() { return courses.map(({ slug }) => ({ slug })); }

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const course = getCourse((await params).slug);
  return course ? { title: course.title, description: course.description } : {};
}

export default async function CoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const course = getCourse((await params).slug);
  if (!course) notFound();
  const student = await getStudentIdentity();
  const canEnrol = Boolean(student?.emailVerified);
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="relative overflow-hidden bg-[#07152d] text-white"><div className="graph-paper absolute inset-0 opacity-20" /><div className="relative mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-24"><Link href="/courses" className="inline-flex items-center gap-2 text-sm font-semibold text-white/65 hover:text-white"><ArrowLeft className="size-4" /> All courses</Link><div className="mt-10 grid gap-12 lg:grid-cols-[1fr_380px] lg:items-end"><div><div className="flex flex-wrap gap-2"><span className="rounded-full bg-[#2767d8] px-3 py-1 text-xs font-bold">{course.curriculum}</span><span className="rounded-full border border-white/20 px-3 py-1 text-xs font-bold text-white/70">{course.level}</span></div><h1 className="mt-6 max-w-4xl text-5xl font-semibold leading-[1.02] tracking-[-.05em] sm:text-6xl">{course.title}</h1><p className="mt-6 max-w-2xl text-lg leading-8 text-white/68">{course.description}</p><div className="mt-8 flex flex-wrap gap-6 text-sm text-white/65"><span className="flex items-center gap-2"><BookOpen className="size-4 text-[#ffcc66]" />{course.lessons} lessons</span><span className="flex items-center gap-2"><Clock3 className="size-4 text-[#ffcc66]" />{course.hours} guided hours</span></div></div><aside className="rounded-3xl border border-white/15 bg-white/10 p-6 backdrop-blur"><p className="text-sm text-white/60">Complete course access</p><p className="mt-1 text-4xl font-bold text-[#ffcc66]">{formatRand(course.price)}</p><p className="mt-4 text-sm leading-6 text-white/60">{canEnrol ? "Your verified profile is ready. Continue from your dashboard before secure PayFast checkout." : "Register and verify your email before continuing to secure PayFast checkout."}</p><Link href={canEnrol ? "/dashboard" : "/register"} className="mt-6 flex items-center justify-center gap-2 rounded-full bg-[#ffcc66] px-6 py-3.5 font-bold text-[#07152d]">{canEnrol ? "Continue to enrol" : "Register to enrol"} <ArrowRight className="size-4" /></Link><div className="mt-4 flex items-center justify-center gap-2 text-xs text-white/55"><ShieldCheck className="size-4" /> Verified students only</div></aside></div></div></section><section className="mx-auto grid max-w-7xl gap-10 px-5 py-16 lg:grid-cols-[.9fr_1.1fr] lg:px-8 lg:py-24"><div><p className="eyebrow">What you will achieve</p><h2 className="mt-4 text-4xl font-semibold tracking-[-.04em]">Build confidence that carries into assessment.</h2><div className="mt-8 grid gap-4">{course.outcomes.map((outcome) => <div key={outcome} className="flex gap-3 rounded-2xl border border-[#dce4ef] bg-white p-4"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[#20a68a]" /><span className="text-sm leading-6 text-[#46556e]">{outcome}</span></div>)}</div></div><div className="rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9"><p className="text-sm font-bold uppercase tracking-[.16em] text-[#1f5bbd]">Course structure</p><div className="mt-6 divide-y divide-[#e2e8f0]">{course.modules.map((module, index) => <div key={module} className="flex items-center gap-5 py-5"><span className="font-mono text-sm text-[#98a4b5]">{String(index + 1).padStart(2,'0')}</span><div><h3 className="font-semibold">{module}</h3><p className="mt-1 text-sm text-[#6a7890]">Video explanation · worked examples · practice</p></div></div>)}</div></div></section><Footer /></main>;
}
