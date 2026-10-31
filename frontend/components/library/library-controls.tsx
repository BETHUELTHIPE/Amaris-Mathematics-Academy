"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Upload, Eye, EyeOff } from "lucide-react";

function errorText(body: Record<string, unknown>): string {
  return Object.entries(body).map(([key, value]) => `${key === "detail" ? "" : `${key}: `}${Array.isArray(value) ? value.join(" ") : String(value)}`).join(" ").slice(0, 600);
}
const fieldClass = "mt-2 min-h-12 w-full rounded-xl border border-[#cbd7e7] bg-white px-4 py-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1f5bbd]";

export function LibraryUpload() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    setFailed(false); setNotice("");
    if (!(file instanceof File) || !file.size || file.size > 50 * 1024 * 1024) {
      setFailed(true); setNotice("Choose a non-empty document no larger than 50 MB."); return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/library/upload", { method: "POST", body: data });
      const body = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(errorText(body));
      form.reset(); setNotice("Document uploaded. Students can now find it in their Library."); router.refresh();
    } catch (error) {
      setFailed(true); setNotice(error instanceof Error ? error.message : "The upload was not confirmed. Refresh the Library before retrying.");
    } finally { setBusy(false); }
  }
  return <details className="rounded-2xl border border-[#cbd7e7] bg-white p-5 sm:p-7">
    <summary className="cursor-pointer text-lg font-semibold text-[#0b2a5b]"><Upload aria-hidden="true" className="mr-2 inline size-5" />Upload a document for students</summary>
    <form onSubmit={submit} className="mt-6 grid gap-5" aria-busy={busy}>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="text-sm font-semibold">Document title<input name="title" required maxLength={180} className={fieldClass} placeholder="e.g. Grade 12 Algebra Workbook" /></label>
        <label className="text-sm font-semibold">Document type<select name="resource_type" required className={fieldClass}><option value="textbook">Textbook</option><option value="worksheet">Worksheet</option><option value="notes">Study notes</option><option value="other">Other document</option></select></label>
        <label className="text-sm font-semibold">Subject<input name="subject" required maxLength={100} className={fieldClass} placeholder="e.g. Mathematics" /></label>
        <label className="text-sm font-semibold">Grade, level or module<input name="level" required maxLength={100} className={fieldClass} placeholder="e.g. Grade 12, N3 or MAT1512" /></label>
      </div>
      <label className="text-sm font-semibold">Description (optional)<textarea name="description" maxLength={2000} rows={3} className={fieldClass} placeholder="Help students choose the right document." /></label>
      <label className="text-sm font-semibold">Document<input type="file" name="file" required accept=".pdf,.docx,.xlsx,.pptx,.txt" className={`${fieldClass} file:mr-3 file:rounded-lg file:border-0 file:bg-[#edf3ff] file:px-3 file:py-2 file:font-semibold`} aria-describedby="library-file-help" /></label>
      <p id="library-file-help" className="text-sm text-[#60708a]">PDF, DOCX, XLSX, PPTX or TXT. Maximum 50 MB per document.</p>
      <label className="flex items-start gap-3 text-sm leading-6"><input type="checkbox" name="sharing_permitted" value="true" required className="mt-1 size-4 shrink-0" />I have permission to share this document with Amaris students.</label>
      <input type="hidden" name="is_published" value="true" />
      <button disabled={busy} className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-semibold text-white disabled:opacity-60">{busy ? "Uploading document…" : "Upload to Library"}</button>
      {notice && <p role={failed ? "alert" : "status"} className={`rounded-xl p-4 text-sm ${failed ? "bg-[#fff3f3] text-[#9b2525]" : "bg-[#ebfbf4] text-[#136950]"}`}>{notice}</p>}
    </form>
  </details>;
}
export function LibraryPublication({ id, published }: { id: string; published: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function toggle() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/library/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_published: !published }) });
      if (!response.ok) throw new Error("Could not update this document. Please try again.");
      router.refresh();
    } catch { setError("Could not update this document. Please try again."); }
    finally { setBusy(false); }
  }
  const Icon = published ? EyeOff : Eye;
  return <div><button onClick={toggle} disabled={busy} className="mt-3 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-[#31537e] disabled:opacity-60"><Icon aria-hidden="true" className="size-4" />{busy ? "Saving…" : published ? "Hide from students" : "Publish for students"}</button>{error && <p role="alert" className="text-sm text-[#9b2525]">{error}</p>}</div>;
}
