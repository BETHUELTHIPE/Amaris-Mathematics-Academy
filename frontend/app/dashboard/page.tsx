import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Bell,
  BookOpen,
  CheckCircle2,
  CreditCard,
  LayoutDashboard,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { courses } from "@/lib/courses";
import { getStudentCourses } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Student Dashboard",
  robots: { index: false, follow: false },
};

export default async function DashboardPage() {
  const user = await requireVerifiedStudent("/dashboard");
  const firstName = user.firstName;
  const profileSaved = user.emailVerified;
  const recommended = courses.slice(0, 2);

  let enrolledCourses: Awaited<ReturnType<typeof getStudentCourses>> = [];
  let courseServiceAvailable = true;
  try {
    enrolledCourses = await getStudentCourses();
  } catch {
    courseServiceAvailable = false;
  }

  const lessonsStarted = enrolledCourses.filter((item) => item.resume.last_lesson).length;

  return <main className="min-h-screen bg-[#f5f7fb]">
    <Header />
    <section className="border-b border-[#dce4ef] bg-white">
      <div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 px-5 py-10 sm:flex-row sm:items-end lg:px-8">
        <div>
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-.045em] sm:text-5xl">Welcome, {firstName}.</h1>
          <p className="mt-3 text-[#60708a]">Your next mathematics step will always be clear here.</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold ${profileSaved ? "bg-[#daf5ec] text-[#13715f]" : "bg-[#fff3d6] text-[#7b5710]"}`}>
          {profileSaved ? <CheckCircle2 className="size-4" /> : <ShieldCheck className="size-4" />}
          {profileSaved ? "Email verified · profile active" : "Email verified"}
        </div>
      </div>
    </section>

    <section className="mx-auto grid max-w-7xl gap-7 px-5 py-10 lg:grid-cols-[240px_1fr] lg:px-8">
      <aside className="h-fit rounded-2xl border border-[#dce4ef] bg-white p-3">
        <nav className="grid gap-1" aria-label="Dashboard navigation">
          {[
            [LayoutDashboard, "Overview", null],
            [BookOpen, "My courses", null],
            [CreditCard, "Orders & payments", null],
            [Bell, "Notifications", null],
            [UserRound, "Profile & security", "/reset-password"],
          ].map(([Icon, label, href], i) => {
            const C = Icon as typeof LayoutDashboard;
            const content = <><C className="size-4" />{label as string}</>;
            return href
              ? <Link key={label as string} href={href as string} className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-[#60708a] hover:bg-[#edf3ff]">{content}</Link>
              : <span key={label as string} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold ${i === 0 ? "bg-[#0b2a5b] text-white" : "text-[#60708a]"}`}>{content}</span>;
          })}
        </nav>
      </aside>

      <div className="min-w-0">
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ["Active courses", String(enrolledCourses.length)],
            ["Lessons started", String(lessonsStarted)],
            ["Certificates earned", "0"],
          ].map(([label, value]) => <div key={label} className="rounded-2xl border border-[#dce4ef] bg-white p-6">
            <p className="text-sm text-[#60708a]">{label}</p>
            <p className="mt-3 text-4xl font-bold tracking-tight">{value}</p>
          </div>)}
        </div>

        {!courseServiceAvailable && <div className="mt-6 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm text-[#765314]">
          Course progress is temporarily unavailable. Your verified account remains secure; try again shortly.
        </div>}

        {enrolledCourses.length > 0 ? <section className="mt-6 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9">
          <p className="eyebrow">My courses</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-.035em]">Continue where you stopped.</h2>
          <div className="mt-6 grid gap-4">
            {enrolledCourses.map(({ course, resume }) => {
              const lesson = resume.last_lesson;
              const href = lesson
                ? `/learn/${course.slug}/${lesson.slug}?t=${resume.last_position_seconds}`
                : `/courses/${course.slug}`;
              return <Link key={course.slug} href={href} className="group rounded-2xl border border-[#dce4ef] p-5 transition hover:border-[#aac3ec] hover:bg-[#f8fbff]">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold">{course.title}</h3>
                    <p className="mt-1 text-sm text-[#60708a]">
                      {lesson ? `Resume: ${lesson.title} · ${resume.progress_percent}% complete` : "Start your first lesson"}
                    </p>
                  </div>
                  <ArrowRight className="size-5 text-[#1f5bbd] transition group-hover:translate-x-1" />
                </div>
              </Link>;
            })}
          </div>
        </section> : <div className="mt-6 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9">
          <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <span className="inline-flex rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">Ready when you are</span>
              <h2 className="mt-5 text-3xl font-semibold tracking-[-.035em]">Your course shelf is waiting.</h2>
              <p className="mt-3 max-w-xl text-sm leading-7 text-[#60708a]">After PayFast verifies a purchase, the course appears here with a Continue Learning button and your last saved lesson position.</p>
            </div>
            <Link href="/courses" className="inline-flex items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3.5 font-bold text-white">Choose a course <ArrowRight className="size-4" /></Link>
          </div>
        </div>}

        <section className="mt-8">
          <div className="flex items-end justify-between">
            <div><p className="eyebrow">Recommended next</p><h2 className="mt-2 text-2xl font-semibold">Popular starting points</h2></div>
            <Link href="/courses" className="text-sm font-bold text-[#1f5bbd]">View all</Link>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {recommended.map((course) => <Link key={course.slug} href={`/courses/${course.slug}`} className="group rounded-2xl border border-[#dce4ef] bg-white p-6 transition hover:-translate-y-1 hover:shadow-lg">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span>
                <ArrowRight className="size-4 text-[#60708a] transition group-hover:translate-x-1" />
              </div>
              <h3 className="mt-5 text-xl font-semibold">{course.title}</h3>
              <p className="mt-2 text-sm text-[#60708a]">{course.lessons} lessons · {course.hours} hours</p>
            </Link>)}
          </div>
        </section>
      </div>
    </section>
    <Footer />
  </main>;
}
