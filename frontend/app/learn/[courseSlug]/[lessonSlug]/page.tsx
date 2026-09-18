import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { studentApi } from "@/lib/backend";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { LessonProgressTracker } from "@/components/site/lesson-progress-tracker";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Lesson", robots: { index: false, follow: false } };

type LessonPayload = {
  course_slug: string;
  course_title: string;
  lesson_slug: string;
  title: string;
  summary: string;
  lesson_body: string;
  duration_minutes: number;
  video_url: string | null;
  position_seconds: number;
};

export default async function LessonPage({ params }: { params: Promise<{ courseSlug: string; lessonSlug: string }> }) {
  const { courseSlug, lessonSlug } = await params;
  await requireVerifiedStudent(`/learn/${courseSlug}/${lessonSlug}`);
  const lesson = await studentApi<LessonPayload>(
    `/student/courses/${encodeURIComponent(courseSlug)}/lessons/${encodeURIComponent(lessonSlug)}/`,
  );
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><article className="mx-auto max-w-4xl px-5 py-12 lg:px-8 lg:py-20"><Link href="/dashboard" className="inline-flex items-center gap-2 text-sm font-semibold text-[#52617a]"><ArrowLeft className="size-4" /> Dashboard</Link><p className="eyebrow mt-8">{lesson.course_title}</p><h1 className="mt-3 text-4xl font-semibold tracking-[-.04em] sm:text-5xl">{lesson.title}</h1>{lesson.summary && <p className="mt-5 text-lg leading-8 text-[#60708a]">{lesson.summary}</p>}<LessonProgressTracker courseSlug={courseSlug} lessonSlug={lessonSlug} videoUrl={lesson.video_url} initialPositionSeconds={lesson.position_seconds} /><div className="mt-9 whitespace-pre-wrap rounded-3xl border border-[#dce4ef] bg-white p-7 text-base leading-8 text-[#263951] sm:p-10">{lesson.lesson_body || "Lesson notes are being prepared."}</div></article><Footer /></main>;
}
