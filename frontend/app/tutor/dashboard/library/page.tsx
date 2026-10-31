import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getStudentIdentity } from "@/lib/auth";
import { getLibrary, LibraryError, type LibraryPage } from "@/lib/library-api";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { LibraryShelf } from "@/components/library/library-shelf";
import { LibraryUpload } from "@/components/library/library-controls";
export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Library — Tutor Dashboard", robots: { index: false, follow: false } };
export default async function TutorLibraryPage({ searchParams }: { searchParams: Promise<{ q?: string; resource_type?: string; page?: string }> }) {
  const identity = await getStudentIdentity();
  if (!identity) redirect("/tutor/login");
  if (!identity.emailVerified) redirect(`/tutor/verify-email?email=${encodeURIComponent(identity.email)}`);
  const query = await searchParams;
  let data: LibraryPage | null = null;
  let message = "The Library is temporarily unavailable. Please refresh this page shortly.";
  try { data = await getLibrary("tutor", query); } catch (error) { if (error instanceof LibraryError) message = error.message; }
  return <main className="min-h-screen min-w-0 bg-[#f5f7fb]"><Header />
    <section className="bg-[#07152d] px-5 py-10 text-white"><div className="mx-auto max-w-6xl"><Link href="/tutor/dashboard" className="inline-block min-h-11 py-3 text-sm font-semibold text-[#ffcc66]">← Tutor dashboard</Link><h1 className="mt-3 text-4xl font-semibold">Library</h1><p className="mt-4 max-w-2xl text-sm leading-7 text-white/75">Share textbooks, worksheets and study notes. Published documents appear in each student’s Library. You can hide your own uploads at any time.</p></div></section>
    <div className="mx-auto max-w-6xl space-y-7 px-5 py-10">{data ? <><LibraryUpload /><LibraryShelf data={data} role="tutor" query={query} /></> : <div role="alert" className="rounded-2xl border border-[#f2d28d] bg-[#fff8e7] p-6 text-[#765314]">{message}</div>}</div><Footer />
  </main>;
}
