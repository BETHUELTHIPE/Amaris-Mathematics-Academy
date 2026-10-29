import Link from "next/link";
import { AlertCircle, ArrowUpRight, Check, Clock3, CircleDot } from "lucide-react";
import type { StudentCourse, StudentOrder } from "@/lib/student-api";
import { studentWorkflow } from "@/lib/student-workflow-states";
import { StudentWorkflowRefresh } from "@/components/site/student-workflow-refresh";

export function StudentWorkflowVisuals({
  orders,
  courses,
  ordersAvailable,
  coursesAvailable,
}: {
  orders: StudentOrder[];
  courses: StudentCourse[];
  ordersAvailable: boolean;
  coursesAvailable: boolean;
}) {
  // These records are fetched through the authenticated student-scoped Django API.
  // Never embed operational Airflow/Grafana consoles or infrastructure credentials.
  const accessibleCourseHrefs = new Set(
    courses.map(({ course }) => "/courses/" + encodeURIComponent(course.slug)),
  );
  const workflows = orders.slice(0, 4).map((order) =>
    studentWorkflow(order, coursesAvailable && accessibleCourseHrefs.has(order.href)),
  );

  return <section id="my-workflows" aria-labelledby="student-workflows-heading" className="mt-6 min-w-0 scroll-mt-36 rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
      <div className="min-w-0">
        <p className="eyebrow">Your activity in progress</p>
        <h2 id="student-workflows-heading" className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">My learning workflows</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#60708a]">
          Follow the verified stages of your purchases, live classes and requested videos. Only your own academy records appear here.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
      <StudentWorkflowRefresh />
      <Link href="/dashboard/orders" className="inline-flex min-h-11 shrink-0 items-center gap-2 self-start rounded-full border border-[#bfd0e8] px-4 text-sm font-bold text-[#194f95]">
        All activity <ArrowUpRight aria-hidden="true" className="size-4" />
      </Link>
      </div>
    </div>

    {!ordersAvailable ? <div role="status" className="mt-5 rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-4 text-sm leading-6 text-[#765314]">
      Workflow status is temporarily unavailable. No milestones are being estimated. Your bookings and payments are not changed.
    </div> : workflows.length === 0 ? <div className="mt-5 rounded-2xl bg-[#f5f8fd] p-5 text-sm leading-6 text-[#60708a]">
      No service workflows yet. When you purchase a course, book a class or request a topical video, its stages will appear here.
    </div> : <div className="mt-5 grid gap-4">
      {workflows.map((workflow) => <article key={workflow.kind + "-" + workflow.reference} className="min-w-0 rounded-2xl border border-[#dce4ef] bg-[#fbfcff] p-4 sm:p-5">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#315e9b]">
              {workflow.kind === "video_request" ? "Requested video" : workflow.kind === "live_class" ? "Online class" : "Course purchase"}
            </p>
            <h3 className="mt-1 break-words text-lg font-bold [overflow-wrap:anywhere]">{workflow.title}</h3>
            <p className={"mt-2 text-sm font-semibold " + (workflow.attention ? "text-[#a52828]" : "text-[#355675]")}>
              Status: {workflow.statusLabel}
            </p>
            <p className="mt-1 text-xs text-[#60708a]">{workflow.confirmedCount} of {workflow.totalCount} stages confirmed</p>
          </div>
          <Link href={workflow.detailHref} className="inline-flex min-h-11 shrink-0 items-center gap-2 self-start rounded-full border border-[#bfd0e8] px-4 text-sm font-semibold text-[#194f95]">
            View details <ArrowUpRight aria-hidden="true" className="size-4" />
          </Link>
        </div>
        <ol className="mt-4 grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3" aria-label={"Progress for " + workflow.title}>
          {workflow.milestones.map((milestone, index) => {
            const complete = milestone.state === "complete";
            const attention = milestone.state === "attention";
            const current = milestone.state === "current";
            const Icon = complete ? Check : attention ? AlertCircle : current ? Clock3 : CircleDot;
            const colors = complete ? "border-[#bee7d9] bg-[#effbf6] text-[#116544]"
              : attention ? "border-[#f3b7b7] bg-[#fff2f2] text-[#a52828]"
              : current ? "border-[#b4cff4] bg-[#edf4ff] text-[#20559d]"
              : "border-[#e2e7ef] bg-white text-[#65748c]";
            return <li key={index} aria-current={current && !workflow.attention ? "step" : undefined} className={"flex min-w-0 items-center gap-2 rounded-xl border p-3 text-xs font-semibold " + colors}>
              <Icon aria-hidden="true" className="size-4 shrink-0" />
              <span className="min-w-0 break-words">{milestone.label}</span>
              <span className="sr-only">
                {complete ? "Completed" : attention ? "Needs attention" : current ? "Awaiting confirmation" : "Not yet reached"}
              </span>
            </li>;
          })}
        </ol>
      </article>)}
    </div>}

    {coursesAvailable && courses.length > 0 && <div className="mt-6 border-t border-[#e2eaf3] pt-5">
      <h3 className="text-lg font-semibold">Your course learning progress</h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {courses.slice(0, 2).map(({ course, resume }) => {
          const percent = Math.max(0, Math.min(100, Number.isFinite(resume.progress_percent) ? resume.progress_percent : 0));
          return <div key={course.slug} className="min-w-0 rounded-xl border border-[#dce4ef] p-4">
            <p className="break-words text-sm font-semibold [overflow-wrap:anywhere]">{course.title}</p>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-[#60708a]">
              <span>Recorded learning progress</span><strong className="text-[#0b2a5b]">{percent}%</strong>
            </div>
            <div role="progressbar" aria-label={course.title + " learning progress"} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="mt-2 h-2 overflow-hidden rounded-full bg-[#e6ecf5]">
              <div className="h-full rounded-full bg-[#2867b8]" style={{ width: percent + "%" }} />
            </div>
          </div>;
        })}
      </div>
    </div>}

    <p className="mt-5 text-xs leading-5 text-[#60708a]">
      These stages reflect your private Django student records when the dashboard loads or you refresh. They are not the internal Apache Airflow task graph, and updates may appear after processing is confirmed.
    </p>
  </section>;
}
