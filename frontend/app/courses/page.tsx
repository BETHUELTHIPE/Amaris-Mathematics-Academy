import type { Metadata } from "next";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { CourseBrowser } from "@/components/site/course-browser";
import { getManagedCourseCatalog } from "@/lib/cms";
import { normalizeCatalogOptions } from "@/lib/course-catalog-search.mjs";

export const metadata: Metadata = { title: "Mathematics Courses", description: "Browse mathematics courses for CAPS, IEB, TVET and university study." };

type SearchParams = Record<string, string | string[] | undefined>;

export default async function CoursesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const options = normalizeCatalogOptions({ query: params.q, programme: params.programme, level: params.level, sort: params.sort, page: params.page });
  // A streaming fallback hides the native form until an inline script runs.
  // Resolve the catalogue before rendering so the form also works without JS.
  const catalog = await getManagedCourseCatalog(options);
  return <main className="min-h-screen bg-[#f5f7fb]"><Header /><section className="border-b border-[#dce4ef] bg-white"><div className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20"><p className="eyebrow">Course catalogue</p><div className="mt-4 flex flex-col justify-between gap-6 md:flex-row md:items-end"><h1 className="section-title max-w-3xl">Find your mathematics pathway.</h1><p className="max-w-md text-base leading-8 text-[#60708a]">Search across the full catalogue. Filter by curriculum and level, then sort by best match, price or newest courses.</p></div></div></section><section className="mx-auto max-w-7xl px-5 py-12 lg:px-8 lg:py-16"><CourseBrowser catalog={catalog} options={options} /></section><Footer /></main>;
}

