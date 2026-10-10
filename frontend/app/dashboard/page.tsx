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

  return <main className="min-h-screen min-w-0 bg-[#f5f7fb]">
    <Header />
    <section className="border-b border-[#dce4ef] bg-white">
      <div className="mx-auto flex max-w-7xl min-w-0 flex-col justify-between gap-5 px-4 py-8 sm:px-5 sm:py-10 md:flex-row md:items-end lg:px-8">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Student dashboard</p>
          <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-[-.045em] [overflow-wrap:anywhere] sm:text-4xl lg:text-5xl">Welcome, {firstName}.</h1>
          <p className="mt-3 text-[#60708a]">Your next mathematics step will always be clear here.</p>
        </div>
        <div className={`inline-flex max-w-full self-start items-center gap-2 rounded-2xl px-4 py-2 text-left text-sm font-semibold leading-5 md:shrink-0 ${profileSaved ? "bg-[#daf5ec] text-[#13715f]" : "bg-[#fff3d6] text-[#7b5710]"}`}>
          {profileSaved ? <CheckCircle2 className="size-4" /> : <ShieldCheck className="size-4" />}
          {profileSaved ? "Email verified · profile active" : "Email verified"}
        </div>
      </div>
    </section>

    <section id="student-dashboard-content" className="mx-auto grid max-w-7xl min-w-0 gap-5 px-4 py-6 sm:px-5 sm:py-10 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)] lg:gap-7 lg:px-8">
      <aside className="h-fit min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-3 lg:sticky lg:top-32">
        <nav className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-1 lg:gap-1" aria-label="Dashboard navigation">
          {[
            [LayoutDashboard, "Overview", null],
            [BookOpen, "My courses", "#my-courses"],
            [CreditCard, "Orders & payments", null],
            [Bell, "Notifications", null],
            [UserRound, "Profile & security", "/reset-password"],
          ].map(([Icon, label, href], i) => {
            const C = Icon as typeof LayoutDashboard;
            const content = <><C aria-hidden="true" className="size-4 shrink-0" /><span className="min-w-0 break-words">{label as string}</span></>;
            return href
              ? <Link key={label as string} href={href as string} className="flex min-h-12 min-w-0 items-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold text-[#31537e] transition hover:bg-[#edf3ff] focus-visible:bg-[#edf3ff] lg:gap-3 lg:px-4">{content}</Link>
              : <span key={label as string} aria-current={i === 0 ? "page" : undefined} aria-disabled={i !== 0 ? true : undefined} className={`flex min-h-12 min-w-0 items-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold lg:gap-3 lg:px-4 ${i === 0 ? "bg-[#0b2a5b] text-white" : "text-[#60708a]"}`}>{content}</span>;
          })}
        </nav>
      </aside>

      <div className="min-w-0">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[
            ["Active courses", String(enrolledCourses.length)],
            ["Lessons started", String(lessonsStarted)],
            ["Certificates earned", "0"],
          ].map(([label, value]) => <div key={label} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-5 sm:p-6">
            <p className="text-sm text-[#60708a]">{label}</p>
            <p className="mt-3 text-4xl font-bold tracking-tight">{value}</p>
          </div>)}
        </div>

        {!courseServiceAvailable && <div className="mt-6 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm text-[#765314]">
          Course progress is temporarily unavailable. Your verified account remains secure; try again shortly.
        </div>}

        {enrolledCourses.length > 0 ? <section id="my-courses" className="mt-6 min-w-0 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-9">
          <p className="eyebrow">My courses</p>
          <h2 className="mt-3 text-2xl font-semibold leading-tight tracking-[-.035em] sm:text-3xl">Continue where you stopped.</h2>
          <div className="mt-6 grid gap-4">
            {enrolledCourses.map(({ course, resume }) => {
              const lesson = resume.last_lesson;
              const href = lesson
                ? `/learn/${course.slug}/${lesson.slug}?t=${resume.last_position_seconds}`
                : `/courses/${course.slug}`;
              return <Link key={course.slug} href={href} className="group block min-w-0 rounded-2xl border border-[#dce4ef] p-4 transition hover:border-[#aac3ec] hover:bg-[#f8fbff] focus-visible:border-[#1f5bbd] sm:p-5">
                <div className="flex min-w-0 items-center justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold [overflow-wrap:anywhere]">{course.title}</h3>
                    <p className="mt-1 break-words text-sm text-[#60708a]">
                      {lesson ? `Resume: ${lesson.title} · ${resume.progress_percent}% complete` : "Start your first lesson"}
                    </p>
                  </div>
                  <ArrowRight aria-hidden="true" className="size-5 shrink-0 text-[#1f5bbd] transition group-hover:translate-x-1" />
                </div>
              </Link>;
            })}
          </div>
        </section> : <div id="my-courses" className="mt-6 min-w-0 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-9">
          <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
            <div>
              <span className="inline-flex rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">Ready when you are</span>
              <h2 className="mt-5 text-2xl font-semibold leading-tight tracking-[-.035em] sm:text-3xl">Your course shelf is waiting.</h2>
              <p className="mt-3 max-w-xl text-sm leading-7 text-[#60708a]">After PayFast verifies a purchase, the course appears here with a Continue Learning button and your last saved lesson position.</p>
            </div>
            <Link href="/courses" className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3.5 text-center font-bold text-white sm:w-fit">Choose a course <ArrowRight className="size-4" /></Link>
          </div>
        </div>}

        <section className="mt-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><p className="eyebrow">Recommended next</p><h2 className="mt-2 text-2xl font-semibold">Popular starting points</h2></div>
            <Link href="/courses" className="inline-flex min-h-11 items-center rounded-lg px-2 text-sm font-bold text-[#1f5bbd] hover:underline">View all</Link>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {recommended.map((course) => <Link key={course.slug} href={`/courses/${course.slug}`} className="group block min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-5 transition hover:-translate-y-1 hover:shadow-lg sm:p-6">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span>
                <ArrowRight className="size-4 text-[#60708a] transition group-hover:translate-x-1" />
              </div>
              <h3 className="mt-5 break-words text-xl font-semibold [overflow-wrap:anywhere]">{course.title}</h3>
              <p className="mt-2 text-sm text-[#60708a]">{course.lessons} lessons · {course.hours} hours</p>
            </Link>)}
          </div>
        </section>
      </div>
    </section>
    <Footer />
  </main>;
}
