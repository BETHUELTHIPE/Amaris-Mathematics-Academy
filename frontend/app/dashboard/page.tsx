import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  ShieldCheck,
  Video,
} from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { paginatePrivateRows, PrivatePagination } from "@/components/site/private-pagination";
import { StudentWorkflowVisuals } from "@/components/site/student-workflow-visuals";
import { courses } from "@/lib/courses";
import { getStudentCourses, getStudentOrders, getStudentVideoRequests } from "@/lib/student-api";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Student Dashboard",
  robots: { index: false, follow: false },
};

function StudentDashboardSkeleton() {
  return <div role="status" aria-label="Loading your private dashboard" className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => <div key={index} className="h-32 rounded-2xl border border-[#dce4ef] bg-white p-5">
        <div className="h-4 w-24 rounded bg-[#e9eef6]" />
        <div className="mt-5 h-9 w-16 rounded bg-[#e9eef6]" />
      </div>)}
    </div>
    <div aria-hidden="true" className="min-h-64 rounded-3xl border border-[#dce4ef] bg-white p-6">
      <div className="h-6 w-52 max-w-full rounded bg-[#e9eef6]" />
      <div className="mt-5 h-24 rounded-2xl bg-[#f1f5fa]" />
    </div>
    <span className="sr-only">Loading your courses, orders and learning progress</span>
  </div>;
}

async function StudentDashboardContent({ coursesPage, videosPage }: { coursesPage?: string; videosPage?: string }) {
  const recommended = courses.slice(0, 2);
  // Start independent student-scoped reads together so the workflow panel
  // does not add another serial API round trip to the dashboard loading path.
  const pendingSecondary = Promise.allSettled([
    getStudentVideoRequests(),
    getStudentOrders(),
  ]);

  let enrolledCourses: Awaited<ReturnType<typeof getStudentCourses>> = [];
  let courseServiceAvailable = true;
  try {
    enrolledCourses = await getStudentCourses();
  } catch {
    courseServiceAvailable = false;
  }

  const [videoResult, ordersResult] = await pendingSecondary;
  const videoRequestServiceAvailable = videoResult.status === "fulfilled";
  const videoRequests = videoResult.status === "fulfilled" ? videoResult.value : [];
  const orderServiceAvailable = ordersResult.status === "fulfilled";
  const orders = ordersResult.status === "fulfilled" ? ordersResult.value : [];

  const lessonsStarted = enrolledCourses.filter((item) => item.resume.last_lesson).length;
  const courseHistory = paginatePrivateRows(enrolledCourses, coursesPage, 8);
  const videoHistory = paginatePrivateRows(videoRequests, videosPage, 8);


  return <>
       <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Active courses", String(enrolledCourses.length)],
            ["Lessons started", String(lessonsStarted)],
            ["Video requests", String(videoRequests.length)],
            ["Certificates earned", "0"],
          ].map(([label, value]) => <div key={label} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-white p-5 sm:p-6">
            <p className="text-sm text-[#60708a]">{label}</p>
            <p className="mt-3 text-4xl font-bold tracking-tight">{value}</p>
          </div>)}
        </div>

        {!courseServiceAvailable && <div className="mt-6 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm text-[#765314]">
          Course progress is temporarily unavailable. Your verified account remains secure; try again shortly.
        </div>}

        {!videoRequestServiceAvailable && <div className="mt-6 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-5 text-sm text-[#765314]">
          Video-request progress is temporarily unavailable. Your documents and paid tickets remain private; try again shortly.
        </div>}

        <StudentWorkflowVisuals
          orders={orders}
          courses={enrolledCourses}
          ordersAvailable={orderServiceAvailable}
          coursesAvailable={courseServiceAvailable}
        />

        {enrolledCourses.length > 0 ? <section id="my-courses" className="mt-6 min-w-0 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-9">
          <p className="eyebrow">My courses</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-.035em]">Continue where you stopped.</h2>
          <div className="mt-6 grid gap-4">
            {courseHistory.rows.map(({ course, resume }) => {
              const lesson = resume.last_lesson;
              const href = lesson
                ? `/learn/${encodeURIComponent(course.slug)}/${encodeURIComponent(lesson.slug)}?t=${resume.last_position_seconds}`
                : course.first_lesson_slug
                  ? `/learn/${encodeURIComponent(course.slug)}/${encodeURIComponent(course.first_lesson_slug)}`
                  : `/courses/${encodeURIComponent(course.slug)}`;
              return <Link key={course.slug} href={href} className="group block min-w-0 rounded-2xl border border-[#dce4ef] p-4 transition hover:border-[#aac3ec] hover:bg-[#f8fbff]">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold [overflow-wrap:anywhere]">{course.title}</h3>
                    <p className="mt-1 text-sm text-[#60708a]">
                      {lesson ? `Resume: ${lesson.title} · ${resume.progress_percent}% complete` : "Start your first lesson"}
                    </p>
                  </div>
                  <ArrowRight className="size-5 text-[#1f5bbd] transition group-hover:translate-x-1" />
                </div>
              </Link>;
            })}
          </div>
          <PrivatePagination basePath="/dashboard" anchor="my-courses" queryKey="courses_page" current={courseHistory.current} totalPages={courseHistory.totalPages} preserve={{ videos_page: videoHistory.current }} />
        </section> : <div id="my-courses" className="mt-6 min-w-0 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-9">
          <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <span className="inline-flex rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">Ready when you are</span>
              <h2 className="mt-5 text-3xl font-semibold tracking-[-.035em]">Your course shelf is waiting.</h2>
              <p className="mt-3 max-w-xl text-sm leading-7 text-[#60708a]">After PayFast verifies a purchase, the course appears here with a Continue Learning button and your last saved lesson position.</p>
            </div>
            <Link href="/courses" className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3.5 text-center font-bold text-white sm:w-fit">Choose a course <ArrowRight className="size-4" /></Link>
          </div>
        </div>}

        <section id="requested-videos" className="mt-8 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-7 sm:p-9">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div><p className="eyebrow">My requested videos</p><h2 className="mt-2 text-2xl font-semibold">Paid queue and completed lessons</h2></div>
            <Link href="/request-a-video" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-5 font-bold text-white"><Video className="size-4" /> Request a topic video</Link>
          </div>
          {videoRequests.length ? <div className="mt-6 grid gap-3">
            {videoHistory.rows.map((item) => <Link key={item.request_reference} href={`/request-a-video/confirmation?reference=${encodeURIComponent(item.request_reference)}`} className="group rounded-2xl border border-[#dce4ef] p-5 transition hover:border-[#aac3ec] hover:bg-[#f8fbff]">
              <div className="flex items-center justify-between gap-4">
                <div><h3 className="font-semibold [overflow-wrap:anywhere]">{item.topic}</h3><p className="mt-1 text-sm text-[#60708a]">{item.status_label}{item.queue_position ? ` · Queue ${item.queue_position}` : ""}{item.ticket_number ? ` · ${item.ticket_number}` : ""}</p></div>
                <ArrowRight className="size-5 text-[#1f5bbd] transition group-hover:translate-x-1" />
              </div>
            </Link>)}
          </div> : <p className="mt-5 text-sm leading-7 text-[#60708a]">No video requests yet. Upload a question, assignment or past paper and choose the explanation you need.</p>}
          <PrivatePagination basePath="/dashboard" anchor="requested-videos" queryKey="videos_page" current={videoHistory.current} totalPages={videoHistory.totalPages} preserve={{ courses_page: courseHistory.current }} />
        </section>

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
              <h3 className="mt-5 break-words text-xl font-semibold [overflow-wrap:anywhere]">{course.title}</h3>
              <p className="mt-2 text-sm text-[#60708a]">{course.lessons} lessons · {course.hours} hours</p>
            </Link>)}
          </div>
        </section>
  </>;
}

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<{ courses_page?: string; videos_page?: string }>;
}) {
  // Authorize before streaming any personal information. Suspense never
  // bypasses the verified student boundary or private no-store API requests.
  const user = await requireVerifiedStudent("/dashboard");
  // Only use identity returned after server-side email verification. Never read
  // names or email addresses from query parameters or local browser storage.
  const fullName = user.displayName.trim();
  const profileSaved = user.emailVerified;
  const { courses_page, videos_page } = await searchParams;
  return <StudentDashboardShell
    active="overview"
    identity={user}
    title={`Welcome, ${fullName}.`}
    description="Your next mathematics step will always be clear here."
    headerAside={<div className={`inline-flex max-w-full self-start items-center gap-2 rounded-2xl px-4 py-2 text-left text-sm font-semibold leading-5 md:shrink-0 ${profileSaved ? "bg-[#daf5ec] text-[#13715f]" : "bg-[#fff3d6] text-[#7b5710]"}`}>
      {profileSaved ? <CheckCircle2 className="size-4" /> : <ShieldCheck className="size-4" />}
      {profileSaved ? "Email verified · profile active" : "Email verified"}
    </div>}
  >
    <Suspense fallback={<StudentDashboardSkeleton />}>
      <StudentDashboardContent coursesPage={courses_page} videosPage={videos_page} />
    </Suspense>
  </StudentDashboardShell>;
}
