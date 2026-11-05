import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseBrowser } from "@/components/site/course-browser";
import { getManagedCourseCatalog } from "@/lib/cms";

export const metadata: Metadata = {
  title: "Mathematics Courses",
  description: "Search and browse the complete Amaris mathematics course catalogue for CAPS, TVET and university students.",
};

type CourseSearchParams = {
  q?: string;
  programme?: string;
  page?: string;
};

export default async function CoursesPage({ searchParams }: { searchParams: Promise<CourseSearchParams> }) {
  const params = await searchParams;
  const query = typeof params.q === "string" ? params.q.trim().slice(0, 100) : "";
  const programme = ["CAPS", "TVET", "University"].includes(params.programme ?? "")
    ? params.programme ?? ""
    : "";
  const requestedPage = Number(params.page ?? "1");
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 && requestedPage <= 100000
    ? requestedPage : 1;
  const catalog = await getManagedCourseCatalog({ page, query, programme });
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="border-b border-[#dce4ef] bg-white">
        <div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20">
          <p className="eyebrow">Course catalogue</p>
          <div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <h1 className="section-title max-w-3xl">Find your mathematics pathway.</h1>
            <p className="max-w-md text-base leading-8 text-[#60708a]">
              Search all available courses, select your programme and browse page by page.
              Every course is organised into clear, measurable steps.
            </p>
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16">
        <CourseBrowser catalog={catalog} query={query} programme={programme} />
      </section>
      <Footer />
    </main>
  );
}
