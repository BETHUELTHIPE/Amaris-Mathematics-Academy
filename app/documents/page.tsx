import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, FileText, ReceiptText, ShieldCheck } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Documents & Invoices", robots: { index: false, follow: false } };

export default async function DocumentsPage() {
  await requireVerifiedStudent("/documents");
  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-6xl px-5 py-12 lg:px-8 lg:py-16">
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm font-semibold text-[#60708a] hover:text-[#0b2a5b]"><ArrowLeft className="size-4" /> Back to dashboard</Link>
        <div className="mt-8 grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div><p className="eyebrow">Student documents</p><h1 className="section-title mt-4">Every document, unmistakably Amaris.</h1><p className="mt-5 max-w-2xl text-lg leading-8 text-[#60708a]">Official communication and invoices use one approved letterhead with the academy logo, contact details and a clear document reference.</p></div>
          <div className="flex items-center gap-3 rounded-2xl border border-[#bcdacb] bg-[#edf9f2] px-5 py-4 text-sm font-semibold text-[#12664d]"><ShieldCheck className="size-5" /> Verified brand format</div>
        </div>
        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <Link href="/documents/letterhead" className="group rounded-3xl border border-[#dce4ef] bg-white p-7 transition hover:-translate-y-1 hover:shadow-xl"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><FileText className="size-6" /></span><h2 className="mt-8 text-2xl font-semibold">Professional letterhead</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Preview and print the approved format for letters, notices, confirmations and learning reports.</p><span className="mt-6 inline-flex text-sm font-bold text-[#1f5bbd]">Open letterhead →</span></Link>
          <Link href="/documents/invoice" className="group rounded-3xl border border-[#dce4ef] bg-white p-7 transition hover:-translate-y-1 hover:shadow-xl"><span className="grid size-12 place-items-center rounded-2xl bg-[#fff4d7] text-[#8a6000]"><ReceiptText className="size-6" /></span><h2 className="mt-8 text-2xl font-semibold">Branded invoice</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Preview the invoice format used for verified purchases, including student and payment references.</p><span className="mt-6 inline-flex text-sm font-bold text-[#1f5bbd]">Open invoice preview →</span></Link>
        </div>
      </section>
      <Footer />
    </main>
  );
}
