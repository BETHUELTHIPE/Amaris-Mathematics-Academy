import Link from "next/link";
import { BookOpen, Download, FileText, Search } from "lucide-react";
import type { LibraryPage, LibraryRole } from "@/lib/library-api";
import { LibraryPublication } from "@/components/library/library-controls";

const labels = { textbook: "Textbook", worksheet: "Worksheet", notes: "Study notes", other: "Document" };
export function LibraryShelf({ data, role, query }: { data: LibraryPage; role: LibraryRole; query: { q?: string; resource_type?: string } }) {
  const base = role === "tutor" ? "/tutor/dashboard/library" : "/dashboard/library";
  function pageLink(page: number) {
    return `${base}?${new URLSearchParams({ q: query.q ?? "", resource_type: query.resource_type ?? "", page: String(page) })}`;
  }
  const pages = Math.max(1, Math.ceil(data.count / data.page_size));
  return <section aria-label="Library documents" className="space-y-6">
    <form action={base} method="get" className="grid gap-4 rounded-2xl border border-[#dce4ef] bg-white p-5 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
      <label className="text-sm font-semibold">Search Library<input type="search" name="q" defaultValue={query.q} maxLength={150} placeholder="Title, subject, grade or module" className="mt-2 min-h-12 w-full rounded-xl border border-[#cbd7e7] px-4 text-sm" /></label>
      <label className="text-sm font-semibold">Document type<select name="resource_type" defaultValue={query.resource_type ?? ""} className="mt-2 min-h-12 w-full rounded-xl border border-[#cbd7e7] px-4 text-sm"><option value="">All documents</option><option value="textbook">Textbooks</option><option value="worksheet">Worksheets</option><option value="notes">Study notes</option><option value="other">Other documents</option></select></label>
      <button className="inline-flex min-h-12 items-center justify-center gap-2 self-end rounded-xl bg-[#0b2a5b] px-5 font-semibold text-white"><Search aria-hidden="true" className="size-4" />Search</button>
    </form>
    <p className="text-sm text-[#60708a]">{data.count} document{data.count === 1 ? "" : "s"} · Page {data.page} of {pages}</p>
    {data.results.length === 0 ? <div className="rounded-2xl border border-dashed border-[#bbcce4] bg-white p-8 text-center"><BookOpen aria-hidden="true" className="mx-auto size-10 text-[#31537e]" /><h2 className="mt-4 text-xl font-semibold">{data.count ? "No documents on this page" : "No documents found"}</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">{query.q || query.resource_type ? "Try another search or choose all document types." : "Textbooks, worksheets and study notes will appear here when your tutors or academy administrators upload them."}</p><Link href={base} className="mt-4 inline-block min-h-11 py-3 text-sm font-semibold text-[#1f5bbd]">View all documents</Link></div> : <div className="grid gap-4 xl:grid-cols-2">
      {data.results.map((item) => <article key={item.id} className="flex min-w-0 flex-col rounded-2xl border border-[#dce4ef] bg-white p-6">
        <div className="flex items-center justify-between gap-3"><span className="inline-flex items-center gap-2 rounded-full bg-[#edf3ff] px-3 py-1 text-xs font-semibold text-[#1f5bbd]"><FileText aria-hidden="true" className="size-4" />{labels[item.resource_type]}</span>{!item.is_published && <span className="text-xs font-semibold text-[#765314]">Hidden from students</span>}</div>
        <h2 className="mt-4 break-words text-xl font-semibold text-[#0b2a5b]">{item.title}</h2>
        <p className="mt-2 break-words text-sm font-semibold text-[#31537e]">{item.subject} · {item.level}</p>
        {item.description && <p className="mt-3 whitespace-pre-line break-words text-sm leading-7 text-[#60708a]">{item.description}</p>}
        <p className="mb-5 mt-4 break-all text-xs text-[#60708a]">{item.original_name} · {(item.size_bytes / (1024 * 1024)).toFixed(2)} MB</p>
        <a href={`/api/library/${item.id}/download?role=${role}`} className="mt-auto inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#0b2a5b] px-5 font-semibold text-white hover:bg-[#123d79]"><Download aria-hidden="true" className="size-4" />Download<span className="sr-only"> {item.title}</span></a>
        {role === "tutor" && item.can_manage && <LibraryPublication id={item.id} published={item.is_published} />}
      </article>)}
    </div>}
    {(data.page > 1 || data.page < pages) && <nav aria-label="Library pages" className="flex justify-between gap-4">{data.page > 1 ? <Link href={pageLink(data.page - 1)} className="min-h-11 rounded-xl border border-[#cbd7e7] bg-white px-5 py-3 text-sm font-semibold">Previous</Link> : <span />}{data.page < pages && <Link href={pageLink(data.page + 1)} className="min-h-11 rounded-xl border border-[#cbd7e7] bg-white px-5 py-3 text-sm font-semibold">Next</Link>}</nav>}
  </section>;
}
