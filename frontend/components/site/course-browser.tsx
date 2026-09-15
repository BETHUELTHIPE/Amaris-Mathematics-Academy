"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, BookOpen, Clock3, Search } from "lucide-react";
import { formatRand, type Course } from "@/lib/courses";

export function CourseBrowser({ courses }: { courses: Course[] }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const filters = ["All", "CAPS", "TVET", "University"];
  const visible = useMemo(() => courses.filter((course) => {
    const matchesText = `${course.title} ${course.description} ${course.curriculum}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All" || (filter === "TVET" ? course.level.includes("TVET") : filter === "University" ? course.level === "University" : course.curriculum.includes(filter));
    return matchesText && matchesFilter;
  }), [courses, query, filter]);

  return (
    <>
      <div className="flex flex-col gap-4 rounded-2xl border border-[#dce4ef] bg-white p-4 shadow-[0_18px_60px_rgba(7,21,45,.06)] sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block flex-1"><span className="sr-only">Search mathematics courses</span><Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[#61708a]" /><input value={query} onChange={(e) => setQuery(e.target.value)} className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] pl-11 pr-4 text-base outline-none transition focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10" placeholder="Search algebra, calculus, Grade 12…" /></label>
        <div className="flex gap-2 overflow-x-auto" aria-label="Course filters">{filters.map((item) => <button key={item} onClick={() => setFilter(item)} className={`whitespace-nowrap rounded-full px-4 py-2.5 text-sm font-semibold transition ${filter === item ? "bg-[#0b2a5b] text-white" : "bg-[#edf2f8] text-[#38465e] hover:bg-[#dfe8f3]"}`}>{item}</button>)}</div>
      </div>
      <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {visible.map((course, index) => (
          <article key={course.slug} className="group flex min-h-[350px] flex-col overflow-hidden rounded-3xl border border-[#dce4ef] bg-white shadow-[0_20px_55px_rgba(7,21,45,.055)] transition hover:-translate-y-1 hover:shadow-[0_24px_70px_rgba(7,21,45,.11)]">
            <div className={`h-2 ${index % 3 === 0 ? "bg-[#2767d8]" : index % 3 === 1 ? "bg-[#ffcc66]" : "bg-[#20a68a]"}`} />
            <div className="flex flex-1 flex-col p-6">
              <div className="flex items-center justify-between gap-3"><span className="rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-bold text-[#1f5bbd]">{course.curriculum}</span><span className="text-sm font-semibold text-[#60708a]">{course.level}</span></div>
              <h2 className="mt-6 text-2xl font-semibold leading-tight tracking-[-0.025em] text-[#0a1b36]">{course.title}</h2>
              <p className="mt-3 text-sm leading-6 text-[#60708a]">{course.description}</p>
              <div className="mt-5 flex gap-4 text-xs font-medium text-[#60708a]"><span className="flex items-center gap-1.5"><BookOpen className="size-4" />{course.lessons} lessons</span><span className="flex items-center gap-1.5"><Clock3 className="size-4" />{course.hours} hours</span></div>
              <div className="mt-auto flex items-end justify-between gap-4 pt-7"><div><span className="text-xs text-[#60708a]">Once-off access</span><p className="text-2xl font-bold text-[#0a1b36]">{formatRand(course.price)}</p></div><Link href={`/courses/${course.slug}`} className="grid size-11 place-items-center rounded-full bg-[#0b2a5b] text-white transition group-hover:bg-[#2767d8]" aria-label={`View ${course.title}`}><ArrowUpRight className="size-5" /></Link></div>
            </div>
          </article>
        ))}
      </div>
      {visible.length === 0 && <div className="mt-8 rounded-2xl border border-dashed border-[#bdc9d8] bg-white p-10 text-center"><p className="font-semibold text-[#0a1b36]">No courses match that search.</p><p className="mt-2 text-sm text-[#60708a]">Try a grade, topic or curriculum name.</p></div>}
    </>
  );
}
