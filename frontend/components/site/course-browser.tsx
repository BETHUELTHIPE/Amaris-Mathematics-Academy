import Link from "next/link";
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Clock3, Search } from "lucide-react";
import { formatRand } from "@/lib/courses";
import type { CourseCatalog } from "@/lib/cms";

const filters = ["All", "CAPS", "TVET", "University"] as const;

type CourseBrowserProps = {
  catalog: CourseCatalog;
  query: string;
  programme: string;
};

function catalogueHref(query: string, programme: string, page = 1): string {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (programme && programme !== "All") params.set("programme", programme);
  if (page > 1) params.set("page", String(page));
  const search = params.toString();
  return search ? `/courses?${search}` : "/courses";
}

export function CourseBrowser({ catalog, query, programme }: CourseBrowserProps) {
  const { courses, count, page, pageSize, hasNext, hasPrevious, available } = catalog;
  const currentFilter = filters.includes(programme as (typeof filters)[number]) ? programme : "All";
  const start = count ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(page * pageSize, count);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  return (
    <>
      <div className="flex flex-col gap-4 rounded-2xl border border-[#dce4ef] bg-white p-4 shadow-[0_18px_60px_rgba(7,21,45,.06)] sm:gap-5">
        <form action="/courses" method="get" role="search" className="flex flex-col gap-3 sm:flex-row">
          <label className="relative block flex-1">
            <span className="sr-only">Search all mathematics courses</span>
            <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[#61708a]" />
            <input
              type="search"
              name="q"
              maxLength={100}
              defaultValue={query}
              className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] pl-11 pr-4 text-base outline-none transition focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10"
              placeholder="Search all courses, e.g. calculus, Grade 12…"
            />
          </label>
          {currentFilter !== "All" && <input type="hidden" name="programme" value={currentFilter} />}
          <button type="submit" className="h-12 rounded-xl bg-[#0b2a5b] px-6 font-semibold text-white hover:bg-[#2767d8]">
            Search courses
          </button>
        </form>
        <nav className="flex gap-2 overflow-x-auto" aria-label="Filter courses by programme">
          {filters.map((item) => (
            <Link
              key={item}
              href={catalogueHref(query, item)}
              aria-current={currentFilter === item ? "page" : undefined}
              className={`whitespace-nowrap rounded-full px-4 py-2.5 text-sm font-semibold transition ${currentFilter === item ? "bg-[#0b2a5b] text-white" : "bg-[#edf2f8] text-[#38465e] hover:bg-[#dfe8f3]"}`}
            >
              {item}
            </Link>
          ))}
        </nav>
      </div>

      {!available ? (
        <div role="alert" className="mt-8 rounded-2xl border border-amber-300 bg-white p-8 text-center">
          <h2 className="font-semibold text-[#0a1b36]">The course catalogue is temporarily unavailable.</h2>
          <p className="mt-2 text-sm text-[#60708a]">Please try again shortly. No purchases can be started from this page right now.</p>
          <Link href="/courses" className="mt-4 inline-block font-semibold text-[#2767d8] underline">Retry loading courses</Link>
        </div>
      ) : (
        <>
          <p className="mt-6 text-sm text-[#60708a]" aria-live="polite">
            {count ? `Showing ${start}–${end} of ${count.toLocaleString("en-ZA")} courses` : "No courses found"}
            {query ? ` for “${query}”` : ""}
          </p>
          <div className="mt-4 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {courses.map((course, index) => (
              <article key={course.slug} className="group flex min-h-[350px] flex-col overflow-hidden rounded-3xl border border-[#dce4ef] bg-white shadow-[0_20px_55px_rgba(7,21,45,.055)] transition hover:-translate-y-1 hover:shadow-[0_24px_70px_rgba(7,21,45,.11)]">
                <div className={`h-2 ${index % 3 === 0 ? "bg-[#2767d8]" : index % 3 === 1 ? "bg-[#ffcc66]" : "bg-[#20a68a]"}`} />
                <div className="flex flex-1 flex-col p-6">
                  <div className="flex items-center justify-between gap-3">
                    <span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span>
                    <span className="text-sm font-semibold text-[#60708a]">{course.level}</span>
                  </div>
                  <h2 className="mt-6 text-2xl font-semibold leading-tight tracking-[-0.025em] text-[#0a1b36]">{course.title}</h2>
                  <p className="mt-3 text-sm leading-6 text-[#60708a]">{course.description}</p>
                  <div className="mt-5 flex gap-4 text-xs font-medium text-[#60708a]">
                    <span className="flex items-center gap-1.5"><BookOpen className="size-4" />{course.lessons} lessons</span>
                    <span className="flex items-center gap-1.5"><Clock3 className="size-4" />{course.hours} hours</span>
                  </div>
                  <div className="mt-auto flex items-end justify-between gap-4 pt-7">
                    <div><span className="text-xs text-[#60708a]">Once-off access</span><p className="text-2xl font-bold text-[#0a1b36]">{formatRand(course.price)}</p></div>
                    <Link href={`/courses/${course.slug}`} className="grid size-11 place-items-center rounded-full bg-[#0b2a5b] text-white transition group-hover:bg-[#2767d8]" aria-label={`View ${course.title}`}><ArrowUpRight className="size-5" /></Link>
                  </div>
                </div>
              </article>
            ))}
          </div>

          {courses.length === 0 && (
            <div className="mt-8 rounded-2xl border border-dashed border-[#bdc9d8] bg-white p-10 text-center">
              <p className="font-semibold text-[#0a1b36]">No courses match this page or search.</p>
              <p className="mt-2 text-sm text-[#60708a]">Try a different topic, programme or page.</p>
              <Link href={catalogueHref(query, currentFilter)} className="mt-3 inline-block font-semibold text-[#2767d8] underline">Return to first page</Link>
            </div>
          )}

          {count > pageSize && (
            <nav className="mt-10 flex flex-wrap items-center justify-between gap-4" aria-label="Course catalogue pages">
              {hasPrevious ? (
                <Link href={catalogueHref(query, currentFilter, page - 1)} rel="prev" className="inline-flex items-center gap-2 rounded-full border border-[#d7e0ec] bg-white px-5 py-3 font-semibold text-[#0b2a5b] hover:bg-[#edf2f8]">
                  <ArrowLeft className="size-4" /> Previous
                </Link>
              ) : <span />}
              <form action="/courses" method="get" className="flex items-center gap-2" aria-label="Jump to a course catalogue page">
                {query && <input type="hidden" name="q" value={query} />}
                {currentFilter !== "All" && <input type="hidden" name="programme" value={currentFilter} />}
                <label htmlFor="course-page-number" className="text-sm font-medium text-[#60708a]">Page</label>
                <input
                  id="course-page-number"
                  name="page"
                  type="number"
                  min={1}
                  max={totalPages}
                  defaultValue={page}
                  className="w-20 rounded-lg border border-[#d7e0ec] bg-white px-2 py-2 text-sm text-[#0b2a5b]"
                />
                <span className="text-sm text-[#60708a]">of {totalPages}</span>
                <button type="submit" className="rounded-lg bg-[#edf2f8] px-3 py-2 text-sm font-semibold text-[#0b2a5b] hover:bg-[#dfe8f3]">Go</button>
              </form>
              {hasNext ? (
                <Link href={catalogueHref(query, currentFilter, page + 1)} rel="next" className="inline-flex items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 font-semibold text-white hover:bg-[#2767d8]">
                  Next <ArrowRight className="size-4" />
                </Link>
              ) : <span />}
            </nav>
          )}
        </>
      )}
    </>
  );
}
