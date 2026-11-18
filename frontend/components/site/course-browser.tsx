import Link from "next/link";
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Clock3, Search, X } from "lucide-react";
import { formatRand } from "@/lib/courses";
import type { CourseCatalog, CourseCatalogOptions } from "@/lib/cms";
import { catalogueHref, COURSE_PROGRAMMES, normalizeCatalogOptions } from "@/lib/course-catalog-search.mjs";

type Props = { catalog: CourseCatalog; options: CourseCatalogOptions };
const suggestedTopics = ["Algebra", "Calculus", "Grade 12", "N4", "Maths lit"];
const commonLevels = [...Array.from({ length: 6 }, (_, i) => `Grade ${i + 7}`), ...Array.from({ length: 6 }, (_, i) => `TVET N${i + 1}`), "Level 2", "Level 3", "Level 4", "University"];

export function CourseBrowser({ catalog, options }: Props) {
  const selected = normalizeCatalogOptions(options);
  const { query, programme, level, sort } = selected;
  const { courses, count, page, pageSize, hasNext, hasPrevious, available, validationError } = catalog;
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  const href = (changes: Record<string, unknown> = {}) => catalogueHref({ ...selected, ...changes });
  const first = count ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, count);

  return <>
    <section id="course-search" className="scroll-mt-36 rounded-2xl border border-[#dce4ef] bg-white p-5 shadow-[0_18px_60px_rgba(7,21,45,.06)] sm:p-6" aria-labelledby="course-search-heading">
      <h2 id="course-search-heading" className="text-lg font-semibold text-[#0a1b36]">Search the full course catalogue</h2>
      <p id="course-search-help" className="mt-1 text-sm leading-6 text-[#60708a]">Try a topic, module, curriculum or grade. You can also search “maths matric” or “gr.12 calculus”. Use up to eight words.</p>
      <form action="/courses" method="get" role="search" aria-label="Find mathematics courses" className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
        <label className="grid min-w-0 gap-2 text-sm font-semibold text-[#263852]">
          Topic or course name
          <span className="relative block">
            <Search aria-hidden="true" className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[#61708a]" />
            <input type="search" name="q" defaultValue={query} maxLength={100} aria-describedby="course-search-help" placeholder="e.g. calculus, maths lit, MAT1503" className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] pl-11 pr-4 text-base font-normal outline-none focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10" />
          </span>
        </label>
        <label className="grid min-w-0 gap-2 text-sm font-semibold text-[#263852]">
          Grade or level
          <input name="level" defaultValue={level} maxLength={100} list="course-level-options" placeholder="All levels" className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] px-4 text-base font-normal outline-none focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10" />
        </label>
        <datalist id="course-level-options">{commonLevels.map(value => <option key={value} value={value} />)}</datalist>
        <label className="grid min-w-0 gap-2 text-sm font-semibold text-[#263852]">
          Sort results
          <select name="sort" defaultValue={sort} className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] px-3 text-base font-normal outline-none focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10">
            <option value="relevance">Best match</option>
            <option value="price">Price: low to high</option>
            <option value="-price">Price: high to low</option>
            <option value="title">Course name: A–Z</option>
            <option value="-created_at">Newest courses</option>
          </select>
        </label>
        {programme !== "All" && <input type="hidden" name="programme" value={programme} />}
        <button type="submit" className="flex h-12 items-center justify-center gap-2 self-end rounded-xl bg-[#0b2a5b] px-6 font-semibold text-white transition hover:bg-[#2767d8] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2767d8]">Search courses <ArrowRight aria-hidden="true" className="size-4" /></button>
      </form>
      <nav className="mt-5 flex flex-wrap items-center gap-2" aria-label="Filter courses by programme">
        {COURSE_PROGRAMMES.map(value => <Link key={value} href={href({ programme: value, page: 1 })} aria-current={programme === value ? "page" : undefined} className={`inline-flex min-h-11 items-center rounded-full px-4 py-2 text-sm font-semibold transition ${programme === value ? "bg-[#0b2a5b] text-white" : "bg-[#edf2f8] text-[#38465e] hover:bg-[#dfe8f3]"}`}>{value}</Link>)}
        {(query || level || programme !== "All" || sort !== "relevance") && <Link href="/courses" className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-sm font-semibold text-[#1f5bbd] underline underline-offset-4"><X aria-hidden="true" className="size-4" />Clear all</Link>}
      </nav>
    </section>

    {validationError ? <div role="alert" className="mt-7 rounded-2xl border border-[#f5c2bf] bg-white p-6 text-[#9b2525]">{validationError}</div> : !available ? <div role="alert" className="mt-7 rounded-2xl border border-amber-300 bg-white p-7 text-center">
      <h2 className="font-semibold text-[#0a1b36]">We couldn’t load these courses.</h2>
      <p className="mt-2 text-sm leading-6 text-[#60708a]">The catalogue may be temporarily unavailable, or this page no longer exists. No sample courses are shown as live products.</p>
      <Link href={href({ page: 1 })} className="mt-4 inline-flex min-h-11 items-center font-semibold text-[#1f5bbd] underline">Retry from the first page</Link>
    </div> : <>
      <p role="status" aria-live="polite" className="mt-7 text-sm text-[#60708a]">{count ? `Showing ${first}–${last} of ${count.toLocaleString("en-ZA")} courses` : "No courses found"}{query ? ` for “${query}”` : ""}{programme !== "All" ? ` · ${programme}` : ""}{level ? ` · ${level}` : ""}</p>
      <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {courses.map((course, index) => <article key={course.slug} className="group flex min-h-[350px] min-w-0 flex-col overflow-hidden rounded-3xl border border-[#dce4ef] bg-white shadow-[0_20px_55px_rgba(7,21,45,.055)] transition hover:-translate-y-1 hover:shadow-[0_24px_70px_rgba(7,21,45,.11)]">
          <div className={`h-2 ${index % 3 === 0 ? "bg-[#2767d8]" : index % 3 === 1 ? "bg-[#ffcc66]" : "bg-[#20a68a]"}`} />
          <div className="flex flex-1 flex-col p-6">
            <div className="flex flex-wrap items-center justify-between gap-3"><span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span><span className="text-sm font-semibold text-[#60708a]">{course.level}</span></div>
            <h2 className="mt-6 break-words text-2xl font-semibold leading-tight tracking-[-0.025em] text-[#0a1b36]">{course.title}</h2>
            <p className="mt-3 text-sm leading-6 text-[#60708a]">{course.description}</p>
            <div className="mt-5 flex flex-wrap gap-4 text-xs font-medium text-[#60708a]"><span className="flex items-center gap-1.5"><BookOpen aria-hidden="true" className="size-4" />{course.lessons} lessons</span><span className="flex items-center gap-1.5"><Clock3 aria-hidden="true" className="size-4" />{course.hours} hours</span></div>
            <div className="mt-auto flex items-end justify-between gap-4 pt-7"><div><span className="text-xs text-[#60708a]">Once-off access</span><p className="text-2xl font-bold text-[#0a1b36]">{formatRand(course.price)}</p></div><Link href={`/courses/${encodeURIComponent(course.slug)}`} className="grid size-11 place-items-center rounded-full bg-[#0b2a5b] text-white transition group-hover:bg-[#2767d8]" aria-label={`View ${course.title}`}><ArrowUpRight aria-hidden="true" className="size-5" /></Link></div>
          </div>
        </article>)}
      </div>
      {courses.length === 0 && <section className="mt-7 rounded-2xl border border-dashed border-[#bdc9d8] bg-white p-8 text-center" aria-labelledby="no-search-results">
        <h2 id="no-search-results" className="font-semibold text-[#0a1b36]">No courses match these filters.</h2>
        <p className="mt-2 text-sm leading-6 text-[#60708a]">Try fewer words, another curriculum, or clear the grade/level filter. These topics may help:</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">{suggestedTopics.map(topic => <Link key={topic} href={catalogueHref({ query: topic })} className="inline-flex min-h-11 items-center rounded-full bg-[#edf3ff] px-4 text-sm font-semibold text-[#1f5bbd]">{topic}</Link>)}</div>
        <Link href="/courses" className="mt-4 inline-flex min-h-11 items-center font-semibold text-[#1f5bbd] underline">Browse all courses</Link>
      </section>}
      {count > pageSize && <nav className="mt-9 flex flex-wrap items-center justify-between gap-4" aria-label="Course catalogue pages">
        {hasPrevious ? <Link href={href({ page: page - 1 })} rel="prev" className="inline-flex min-h-11 items-center gap-2 rounded-full border border-[#d7e0ec] bg-white px-5 py-3 font-semibold text-[#0b2a5b]"><ArrowLeft aria-hidden="true" className="size-4" />Previous</Link> : <span />}
        <form action="/courses" method="get" className="flex flex-wrap items-center gap-2" aria-label="Jump to a course catalogue page">
          {query && <input type="hidden" name="q" value={query} />}
          {programme !== "All" && <input type="hidden" name="programme" value={programme} />}
          {level && <input type="hidden" name="level" value={level} />}
          {sort !== "relevance" && <input type="hidden" name="sort" value={sort} />}
          <label htmlFor="course-page-number" className="text-sm text-[#60708a]">Page</label>
          <input id="course-page-number" name="page" type="number" min={1} max={totalPages} defaultValue={page} className="min-h-11 w-20 rounded-lg border border-[#d7e0ec] bg-white px-2 text-sm text-[#0b2a5b]" />
          <span className="text-sm text-[#60708a]">of {totalPages.toLocaleString("en-ZA")}</span>
          <button type="submit" className="min-h-11 rounded-lg bg-[#edf2f8] px-3 text-sm font-semibold text-[#0b2a5b]">Go</button>
        </form>
        {hasNext ? <Link href={href({ page: page + 1 })} rel="next" className="inline-flex min-h-11 items-center gap-2 rounded-full bg-[#0b2a5b] px-5 py-3 font-semibold text-white">Next<ArrowRight aria-hidden="true" className="size-4" /></Link> : <span />}
      </nav>}
    </>}
  </>;
}
