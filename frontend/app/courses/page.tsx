import { Suspense } from "react";
import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseBrowser } from "@/components/site/course-browser";
import { getManagedCourses } from "@/lib/cms";

export const metadata: Metadata = { title: "Mathematics Courses", description: "Browse mathematics courses for CAPS, TVET and university study." };

async function CoursesResults() {
  const courses = await getManagedCourses();
  return <CourseBrowser courses={courses} />;
}

function CourseGridPlaceholder() {
  return (
    <div aria-hidden="true">
      <div className="flex min-h-20 items-center rounded-2xl border border-[#dce4ef] bg-white p-4">
        <div className="h-12 w-full rounded-xl bg-[#edf1f6]" />
      </div>
      <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="min-h-[350px] rounded-3xl border border-[#dce4ef] bg-white p-6">
            <div className="h-6 w-24 rounded-full bg-[#edf3ff]" />
            <div className="mt-8 h-8 w-3/4 rounded-lg bg-[#edf1f6]" />
            <div className="mt-6 h-20 rounded-lg bg-[#edf1f6]" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CoursesPage() {
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="border-b border-[#dce4ef] bg-white"><div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20"><p className="eyebrow">Course catalogue</p><div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end"><h1 className="section-title max-w-3xl">Find your mathematics pathway.</h1><p className="max-w-md text-base leading-8 text-[#60708a]">Choose a curriculum, level and focus area. Every course is organised into clear, measurable steps.</p></div></div></section><section className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16"><Suspense fallback={<CourseGridPlaceholder />}><CoursesResults /></Suspense></section><Footer /></main>;
}
