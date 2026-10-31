import type { Metadata } from "next";
import { requireVerifiedStudent } from "@/lib/auth";
import { getLibrary, type LibraryPage } from "@/lib/library-api";
import { StudentDashboardShell } from "@/components/site/student-dashboard-shell";
import { LibraryShelf } from "@/components/library/library-shelf";
export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Library — Student Dashboard", robots: { index: false, follow: false } };
export default async function StudentLibraryPage({ searchParams }: { searchParams: Promise<{ q?: string; resource_type?: string; page?: string }> }) {
  await requireVerifiedStudent("/dashboard/library");
  const query = await searchParams;
  let data: LibraryPage | null = null;
  try { data = await getLibrary("student", query); } catch { /* Show a retry state, never a misleading empty Library. */ }
  return <StudentDashboardShell active="library" title="Library" description="Your textbooks, worksheets and study notes, shared by Amaris tutors and academy administrators.">
    {data ? <LibraryShelf data={data} role="student" query={query} /> : <div role="alert" className="rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-[#765314]">The Library is temporarily unavailable. Please refresh this page shortly.</div>}
  </StudentDashboardShell>;
}
