import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseBrowser } from "@/components/site/course-browser";

export const metadata: Metadata = { title: "Mathematics Courses", description: "Browse mathematics courses for CAPS, TVET and university study." };

export default function CoursesPage() {
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="border-b border-[#dce4ef] bg-white"><div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20"><p className="eyebrow">Course catalogue</p><div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end"><h1 className="section-title max-w-3xl">Find your mathematics pathway.</h1><p className="max-w-md text-base leading-8 text-[#60708a]">Choose a curriculum, level and focus area. Every course is organised into clear, measurable steps.</p></div></div></section><section className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16"><CourseBrowser /></section><Footer /></main>;
}
