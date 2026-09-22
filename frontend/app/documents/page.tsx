import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Download, FileText, ReceiptText, ShieldCheck, Upload } from "lucide-react";
import { requireVerifiedStudent } from "@/lib/auth";
import { Header } from "@/components/site/header";
import { Footer } from "@/components/site/footer";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  listStudentFiles,
  STUDENT_FILE_CATEGORIES,
  type StudentFileCategory,
} from "@/lib/student-storage";
import { uploadStudentDocumentAction } from "@/app/documents/actions";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Documents & Invoices", robots: { index: false, follow: false } };

const categoryLabels: Record<StudentFileCategory, string> = {
  invoices: "Invoices",
  receipts: "Receipts",
  certificates: "Certificates",
  reports: "Reports",
  letters: "Letters",
  resources: "Learning resources",
  uploads: "Other uploads",
};

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; uploaded?: string }>;
}) {
  await requireVerifiedStudent("/documents");
  const params = await searchParams;
  const files = await listStudentFiles();

  return (
    <main className="min-h-screen bg-[#f5f7fb]">
      <Header />
      <section className="mx-auto max-w-6xl px-5 py-12 lg:px-8 lg:py-16">
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm font-semibold text-[#60708a] hover:text-[#0b2a5b]"><ArrowLeft className="size-4" /> Back to dashboard</Link>

        <div className="mt-8 grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="eyebrow">Student documents</p>
            <h1 className="section-title mt-4">Secure documents, stored in Supabase.</h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-[#60708a]">
              Invoices, receipts, certificates, reports and uploaded documents are kept in a private student folder.
              Access is restricted to your authenticated Amaris account.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-[#bcdacb] bg-[#edf9f2] px-5 py-4 text-sm font-semibold text-[#12664d]"><ShieldCheck className="size-5" /> Private Supabase Storage</div>
        </div>

        {params.error && <Alert variant="destructive" className="mt-7"><AlertDescription>{params.error}</AlertDescription></Alert>}
        {params.uploaded && <Alert className="mt-7 border-[#9fddce] bg-[#effbf7] text-[#126854]"><AlertDescription className="text-[#126854]">Your file was stored securely in Supabase Storage.</AlertDescription></Alert>}

        <div className="mt-10 grid gap-5 md:grid-cols-2">
          <Link href="/documents/letterhead" className="group rounded-3xl border border-[#dce4ef] bg-white p-7 transition hover:-translate-y-1 hover:shadow-xl"><span className="grid size-12 place-items-center rounded-2xl bg-[#edf3ff] text-[#1f5bbd]"><FileText className="size-6" /></span><h2 className="mt-8 text-2xl font-semibold">Professional letterhead</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Preview and print the approved format for letters, notices, confirmations and learning reports.</p><span className="mt-6 inline-flex text-sm font-bold text-[#1f5bbd]">Open letterhead →</span></Link>
          <Link href="/documents/invoice" className="group rounded-3xl border border-[#dce4ef] bg-white p-7 transition hover:-translate-y-1 hover:shadow-xl"><span className="grid size-12 place-items-center rounded-2xl bg-[#fff4d7] text-[#8a6000]"><ReceiptText className="size-6" /></span><h2 className="mt-8 text-2xl font-semibold">Branded invoice</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Preview the invoice format used for verified purchases, including student and payment references.</p><span className="mt-6 inline-flex text-sm font-bold text-[#1f5bbd]">Open invoice preview →</span></Link>
        </div>

        <section className="mt-10 rounded-3xl border border-[#dce4ef] bg-white p-6 shadow-sm sm:p-8" aria-labelledby="secure-file-vault">
          <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <p className="eyebrow">Secure file vault</p>
              <h2 id="secure-file-vault" className="mt-3 text-3xl font-semibold tracking-[-.035em] text-[#07152d]">Store a document</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-[#60708a]">Files are private, limited to 50 MB each, and stored under your authenticated student ID.</p>
            </div>
          </div>

          <form action={uploadStudentDocumentAction} className="mt-7 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 sm:grid-cols-[220px_1fr_auto] sm:items-end">
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              Category
              <select name="category" className="h-12 rounded-xl border border-[#cbd6e5] bg-white px-3" defaultValue="uploads">
                {STUDENT_FILE_CATEGORIES.map((category) => <option key={category} value={category}>{categoryLabels[category]}</option>)}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-semibold text-[#263852]">
              File
              <input name="file" type="file" required className="block min-h-12 w-full rounded-xl border border-[#cbd6e5] bg-white p-2.5 text-sm" />
            </label>
            <button type="submit" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white transition hover:bg-[#163d78]"><Upload className="size-4" /> Upload securely</button>
          </form>

          <div className="mt-8">
            <div className="flex items-center justify-between gap-4">
              <h3 className="text-xl font-semibold text-[#07152d]">Stored files</h3>
              <span className="text-sm text-[#60708a]">{files.length} file{files.length === 1 ? "" : "s"}</span>
            </div>

            {files.length === 0 ? (
              <div className="mt-5 rounded-2xl border border-dashed border-[#cbd6e5] p-8 text-center text-sm text-[#60708a]">No stored files yet. Upload a PDF, image, document, spreadsheet or other digital file above.</div>
            ) : (
              <div className="mt-5 divide-y divide-[#e4eaf2] overflow-hidden rounded-2xl border border-[#dce4ef]">
                {files.map((file) => (
                  <div key={file.path} className="flex flex-col justify-between gap-4 bg-white p-5 sm:flex-row sm:items-center">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-[#07152d]">{displayStoredName(file.name)}</p>
                      <p className="mt-1 text-xs text-[#60708a]">{categoryLabels[file.category]}{file.size ? ` · ${formatBytes(file.size)}` : ""}{file.createdAt ? ` · ${formatDate(file.createdAt)}` : ""}</p>
                    </div>
                    <Link href={`/documents/file?path=${encodeURIComponent(file.path)}`} className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-full border border-[#b8c7da] px-4 text-sm font-bold text-[#0b2a5b] hover:bg-[#f5f7fb]"><Download className="size-4" /> Download</Link>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </section>
      <Footer />
    </main>
  );
}

function displayStoredName(name: string) {
  return name.replace(/^\d{4}-\d{2}-\d{2}T[^-]+-[0-9a-f-]{36}-/i, "");
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-ZA", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Africa/Johannesburg",
  }).format(new Date(value));
}
