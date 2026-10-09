import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { StudentDashboardNavigation } from "@/components/dashboard/student-navigation";
import { requireVerifiedStudent } from "@/lib/auth";
import { getStudentCourses } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "My Courses", robots: { index: false, follow: false } };

export default async function MyCoursesPage() {
  await requireVerifiedStudent("/dashboard/courses");
  let courses: Awaited<ReturnType<typeof getStudentCourses>> = [];
  let available = true;
  try {
    courses = await getStudentCourses();
  } catch {
    available = false;
  }

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto grid max-w-7xl gap-7 px-5 py-12 lg:grid-cols-[240px_1fr] lg:px-8">
        <StudentDashboardNavigation currentPath="/dashboard/courses" />
        <div className="min-w-0">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-4xl font-semibold">My courses</h1>
          <p className="mt-3 text-[#60708a]">Your paid courses, saved lesson position and learning progress.</p>
          {!available ? (
            <div role="status" className="mt-7 rounded-2xl border border-amber-300 bg-amber-50 p-6">
              We cannot load your courses right now. Please try again shortly. Your enrolments remain protected.
            </div>
          ) : courses.length ? (
            <ul className="mt-7 grid gap-4">
              {courses.map(({ course, resume }) => {
                const lesson = resume.last_lesson;
                const href = lesson
                  ? `/learn/${encodeURIComponent(course.slug)}/${encodeURIComponent(lesson.slug)}?t=${resume.last_position_seconds}`
                  : `/courses/${encodeURIComponent(course.slug)}`;
                return (
                  <li key={course.slug} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
                    <h2 className="text-xl font-semibold">{course.title}</h2>
                    <p className="mt-2 text-sm text-[#60708a]">{resume.progress_percent}% complete</p>
                    <progress aria-label={`${course.title} completion`} value={resume.progress_percent} max={100} className="mt-3 h-3 w-full" />
                    <Link href={href} className="mt-4 inline-flex min-h-11 items-center gap-2 font-semibold text-[#1f5bbd]">
                      {lesson ? `Resume ${lesson.title}` : "Open course"} <ArrowRight className="size-4" aria-hidden="true" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="mt-7 rounded-2xl border border-[#dce4ef] bg-white p-7">
              <BookOpen className="size-8 text-[#1f5bbd]" aria-hidden="true" />
              <h2 className="mt-4 text-2xl font-semibold">No active courses yet</h2>
              <p className="mt-3 text-[#60708a]">Courses appear after payment is verified by the server.</p>
              <Link href="/courses" className="mt-5 inline-flex min-h-11 items-center gap-2 font-bold text-[#1f5bbd]">Browse courses <ArrowRight className="size-4" /></Link>
            </div>
          )}
        </div>
      </section>
      <Footer />
    </main>
  );
}
