import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Clock3, Save } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { requireVerifiedStudent } from "@/lib/auth";
import { getProtectedLesson } from "@/lib/student-api";
import { saveLessonProgressAction } from "@/app/learn/actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Lesson", robots: { index: false, follow: false } };

export default async function LessonPage({
  params,
  searchParams,
}: {
  params: Promise<{ courseSlug: string; lessonSlug: string }>;
  searchParams: Promise<{ t?: string }>;
}) {
  await requireVerifiedStudent("/dashboard");
  const { courseSlug, lessonSlug } = await params;
  const query = await searchParams;
  let data: Awaited<ReturnType<typeof getProtectedLesson>>;
  try {
    data = await getProtectedLesson(courseSlug, lessonSlug);
  } catch {
    notFound();
  }

  const requestedPosition = Math.max(0, Number(query.t ?? data.resume.last_position_seconds) || 0);
  const minutes = Math.floor(requestedPosition / 60);
  const seconds = requestedPosition % 60;

  return <main className="min-h-screen bg-[#f5f7fb]"><Header />
    <section className="mx-auto max-w-5xl px-5 py-12 lg:px-8 lg:py-16">
      <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm font-semibold text-[#1f5bbd]"><ArrowLeft className="size-4" />Student dashboard</Link>
      <div className="mt-8 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-10">
        <p className="eyebrow">{data.course_title} · {data.lesson.module}</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-[-.04em]">{data.lesson.title}</h1>
        {data.lesson.summary && <p className="mt-4 text-lg leading-8 text-[#60708a]">{data.lesson.summary}</p>}
        <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-[#edf3ff] px-4 py-2 text-sm font-semibold text-[#1f5bbd]"><Clock3 className="size-4" />Resume position {minutes}:{String(seconds).padStart(2, "0")}</div>
        {data.lesson.video?.provider === "youtube" && data.lesson.video.youtube_video_id && (
          <div className="mt-8 aspect-video overflow-hidden rounded-2xl bg-black">
            <iframe
              title={data.lesson.title}
              className="h-full w-full"
              src={`https://www.youtube-nocookie.com/embed/${data.lesson.video.youtube_video_id}?start=${requestedPosition}`}
              allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        )}
        <article className="prose prose-slate mt-8 max-w-none whitespace-pre-wrap">{data.lesson.lesson_body || "Lesson content is being prepared."}</article>
        <form action={saveLessonProgressAction} className="mt-8 flex flex-wrap items-center gap-3">
          <input type="hidden" name="courseSlug" value={courseSlug} />
          <input type="hidden" name="lessonSlug" value={lessonSlug} />
          <input type="hidden" name="positionSeconds" value={requestedPosition} />
          <input type="hidden" name="progressPercent" value={Math.max(data.resume.progress_percent, 1)} />
          <button type="submit" className="inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white"><Save className="size-4" />Save progress</button>
        </form>
      </div>
    </section><Footer /></main>;
}
