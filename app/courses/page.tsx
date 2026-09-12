import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight, BookOpen, Clock3, Search } from "lucide-react";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { getManagedCourses } from "@/lib/cms";
import { formatRand } from "@/lib/courses";

export const metadata: Metadata = { title: "Mathematics Courses", description: "Browse mathematics courses for CAPS, TVET and university study." };

const pathways = ["All", "CAPS", "TVET", "University"] as const;

export default async function CoursesPage({ searchParams }: { searchParams: Promise<{ q?: string; pathway?: string }> }) {
  const params = await searchParams;
  const courses = await getManagedCourses();
  const query = typeof params.q === "string" ? params.q.trim().slice(0, 100) : "";
  const pathway = pathways.includes(params.pathway as (typeof pathways)[number]) ? params.pathway! : "All";
  const normalizedQuery = query.toLowerCase();
  const visible = courses.filter((course) => {
    const matchesText = `${course.title} ${course.description} ${course.curriculum} ${course.level}`.toLowerCase().includes(normalizedQuery);
    const matchesPathway = pathway === "All" || (pathway === "TVET" ? course.level.includes("TVET") : pathway === "University" ? course.level === "University" : course.curriculum.includes(pathway));
    return matchesText && matchesPathway;
  });

  const pathwayHref = (value: string) => {
    const nextParams = new URLSearchParams();
    if (query) nextParams.set("q", query);
    if (value !== "All") nextParams.set("pathway", value);
    const serialized = nextParams.toString();
    return serialized ? `/courses?${serialized}` : "/courses";
  };

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20">
          <p className="eyebrow">Course catalogue</p>
          <div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <h1 className="section-title max-w-3xl">Find your mathematics pathway.</h1>
            <p className="max-w-md text-base leading-8 text-[#60708a]">Choose a curriculum, level and focus area. Every course is organised into clear, measurable steps.</p>
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
        <div className="rounded-2xl border border-[#dce4ef] bg-white p-4 shadow-[0_18px_60px_rgba(7,21,45,.06)]">
          <form method="get" action="/courses" className="flex flex-col gap-4 sm:flex-row sm:items-center">
            {pathway !== "All" && <input type="hidden" name="pathway" value={pathway} />}
            <label className="relative block flex-1">
              <span className="sr-only">Search mathematics courses</span>
              <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[#61708a]" />
              <input name="q" defaultValue={query} maxLength={100} className="h-12 w-full rounded-xl border border-[#d7e0ec] bg-[#f7f9fc] pl-11 pr-4 text-base outline-none transition focus:border-[#2767d8] focus:ring-4 focus:ring-[#2767d8]/10" placeholder="Search algebra, calculus, Grade 12…" />
            </label>
            <button type="submit" className="h-12 rounded-xl bg-[#0b2a5b] px-5 text-sm font-bold text-white transition hover:bg-[#2767d8]">Search courses</button>
          </form>
          <nav className="mt-4 flex gap-2 overflow-x-auto" aria-label="Course pathways">
            {pathways.map((item) => <Link key={item} href={pathwayHref(item)} aria-current={pathway === item ? "page" : undefined} className={`whitespace-nowrap rounded-full px-4 py-2.5 text-sm font-semibold transition ${pathway === item ? "bg-[#0b2a5b] text-white" : "bg-[#edf2f8] text-[#38465e] hover:bg-[#dfe8f3]"}`}>{item}</Link>)}
          </nav>
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
        {visible.length === 0 && <div className="mt-8 rounded-2xl border border-dashed border-[#bdc9d8] bg-white p-10 text-center"><p className="font-semibold text-[#0a1b36]">No courses match that search.</p><p className="mt-2 text-sm text-[#60708a]">Try a grade, topic or curriculum name.</p><Link href="/courses" className="mt-5 inline-flex rounded-full bg-[#0b2a5b] px-5 py-2.5 text-sm font-bold text-white">Clear search</Link></div>}
      </section>
      <Footer />
    </main>
  );
}
