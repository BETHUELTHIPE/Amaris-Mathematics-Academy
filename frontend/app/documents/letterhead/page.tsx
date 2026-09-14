import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { CommunicationDocument } from "@/components/documents/communication-document";
import { DocumentActions } from "@/components/documents/document-actions";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Letterhead Preview", robots: { index: false, follow: false } };

export default async function LetterheadPage() {
  const user = await requireVerifiedStudent("/documents/letterhead");
  const date = new Intl.DateTimeFormat("en-ZA", { day: "2-digit", month: "long", year: "numeric", timeZone: "Africa/Johannesburg" }).format(new Date());
  return <main className="document-preview min-h-screen bg-[#e9eef5] px-4 py-8 sm:px-6"><div className="print-hidden mx-auto mb-6 flex max-w-[900px] flex-col justify-between gap-4 sm:flex-row sm:items-center"><Link href="/documents" className="inline-flex items-center gap-2 text-sm font-semibold text-[#526078] hover:text-[#0b2a5b]"><ArrowLeft className="size-4" /> Documents</Link><DocumentActions /></div><div className="mx-auto max-w-[900px]"><CommunicationDocument recipientName={user.displayName} recipientEmail={user.email} date={date} /></div></main>;
}
