"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { BrandDocumentFooter, BrandLetterhead } from "@/components/documents/brand-letterhead";

type SavedForm = {
  id: string; kind: string; form_type: string; created_at: string; status: string; review_notes: string;
  details: Record<string, string>; reviewed_at: string | null;
};
const date = (value: string) => new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg" }).format(new Date(value));
const inputClass = "mt-2 min-h-12 w-full min-w-0 rounded-xl border border-[#cbd7eb] bg-white px-3 py-3 font-normal text-[#263852] focus:outline-2 focus:outline-[#1f5bbd]";

export function TutorPersonnelForms() {
  const [kind, setKind] = useState("leave");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [rows, setRows] = useState<SavedForm[]>([]);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const pending = useRef<{ value: string; key: string } | null>(null);
  const loadHistory = useCallback(async (selected: number) => {
    setLoading(true); setHistoryError("");
    try {
      const response = await fetch(`/api/tutor/forms?page=${selected}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Unable to load saved forms. Please retry.");
      const result = await response.json() as { results: SavedForm[]; has_more: boolean };
      setRows(result.results); setMore(result.has_more); setPage(selected);
    } catch { setHistoryError("Unable to load saved forms. Please retry."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void loadHistory(1); }, [loadHistory]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const values: Record<string, unknown> = { kind, declaration: data.get("declaration") === "on" };
    for (const field of ["reason", "handover", "contact_phone", "signature_name", ...(kind === "leave" ? ["start_date", "end_date", "leave_type"] : ["last_teaching_day"])]) values[field] = String(data.get(field) || "").trim();
    const serialized = JSON.stringify(values);
    if (!pending.current || pending.current.value !== serialized) pending.current = { value: serialized, key: crypto.randomUUID() };
    setBusy(true); setError(""); setSuccess("");
    try {
      const response = await fetch("/api/tutor/forms", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...values, idempotency_key: pending.current.key }) });
      const result = await response.json() as SavedForm & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to submit. Retry the same form and details.");
      setSuccess(`Your ${kind === "leave" ? "leave application" : "resignation notice"} is saved for Admin review. Reference: ${result.id}. Download your original PDF under Saved forms.`);
      pending.current = null; form.reset(); await loadHistory(1);
    } catch (problem) { setError(problem instanceof Error ? problem.message : "Connection interrupted. Retry the same form and details."); }
    finally { setBusy(false); }
  }

  return <section id="tutor-personnel-forms" aria-labelledby="personnel-heading" className="min-w-0 space-y-6">
    <div><p className="eyebrow">Tutor administration</p><h2 id="personnel-heading" className="mt-2 text-3xl font-semibold">Leave & resignation forms</h2><p className="mt-3 text-sm leading-7 text-[#60708a]">Submit a confidential form to the academy, keep a copy and track Admin’s response.</p></div>
    <div className="overflow-hidden rounded-3xl border border-[#dce4ef] bg-white">
      <BrandLetterhead documentLabel="Tutor form" />
      <div className="p-5 sm:p-8">
        <div className="flex flex-wrap gap-3" aria-label="Choose form type">
          <button type="button" disabled={busy} aria-pressed={kind === "leave"} onClick={() => { setKind("leave"); setError(""); }} className={`min-h-12 rounded-xl border px-5 font-semibold ${kind === "leave" ? "bg-[#0b2a5b] text-white" : "border-[#cbd7eb]"}`}>Leave application</button>
          <button type="button" disabled={busy} aria-pressed={kind === "resignation"} onClick={() => { setKind("resignation"); setError(""); }} className={`min-h-12 rounded-xl border px-5 font-semibold ${kind === "resignation" ? "bg-[#0b2a5b] text-white" : "border-[#cbd7eb]"}`}>Withdrawal / resignation</button>
        </div>
        <h3 className="mt-7 text-2xl font-semibold">{kind === "leave" ? "Request time away from teaching" : "Submit a resignation notice"}</h3>
        <p className="mt-3 text-sm leading-7 text-[#60708a]">{kind === "leave" ? "Choose the full leave period, including the first and last day. Admin will review your request." : "Tell Admin your proposed last teaching day and how you will hand over outstanding lessons."} Your existing lessons and account stay active until the academy coordinates the next steps. Avoid including medical details or student personal information.</p>
        <form key={kind} onSubmit={submit} className="mt-6">
          <fieldset disabled={busy} className="grid min-w-0 gap-5 disabled:opacity-60">
            <legend className="sr-only">{kind === "leave" ? "Leave application details" : "Resignation notice details"}</legend>
            {kind === "leave" ? <>
              <label className="text-sm font-semibold">Leave type<select name="leave_type" aria-label="Leave type" required className={inputClass} defaultValue=""><option value="" disabled>Choose leave type</option><option value="annual">Annual leave</option><option value="sick">Sick leave</option><option value="personal">Personal / family responsibility</option><option value="study">Study leave</option><option value="other">Other</option></select></label>
              <div className="grid min-w-0 gap-5 sm:grid-cols-2"><label className="min-w-0 text-sm font-semibold">First day of leave<input name="start_date" type="date" required className={inputClass} /></label><label className="min-w-0 text-sm font-semibold">Last day of leave<input name="end_date" type="date" required className={inputClass} /></label></div>
            </> : <label className="min-w-0 text-sm font-semibold">Proposed last teaching day<input name="last_teaching_day" type="date" required className={inputClass} /></label>}
            <label className="text-sm font-semibold">Reason<textarea name="reason" required minLength={10} maxLength={3000} rows={3} className={inputClass} /></label>
            <label className="text-sm font-semibold">Affected lessons and handover plan<textarea name="handover" required minLength={10} maxLength={3000} rows={3} className={inputClass} /><span className="mt-2 block text-xs font-normal leading-5 text-[#60708a]">Use lesson dates or booking references. If no lessons are affected, say so.</span></label>
            <div className="grid gap-5 sm:grid-cols-2"><label className="text-sm font-semibold">Contact number<input name="contact_phone" type="tel" autoComplete="tel" required minLength={7} maxLength={25} className={inputClass} /></label><label className="text-sm font-semibold">Full name as typed signature<input name="signature_name" autoComplete="name" required minLength={2} maxLength={150} className={inputClass} /></label></div>
            <label className="flex items-start gap-3 text-sm leading-6 text-[#43526a]"><input name="declaration" type="checkbox" required className="mt-1 size-5 shrink-0" /><span>I confirm these details are accurate and submit this form to Amaris Mathematics Academy for review.</span></label>
            <button type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-bold text-white">{busy ? "Saving your form…" : kind === "leave" ? "Submit leave application" : "Submit resignation notice"}</button>
          </fieldset>
        </form>
        {error && <p role="alert" className="mt-5 rounded-xl bg-[#fff0f0] p-4 text-sm text-[#9b2525]">{error}</p>}
        {success && <p role="status" className="mt-5 break-words rounded-xl bg-[#ebfbf4] p-4 text-sm leading-6 text-[#136950]">{success}</p>}
      </div>
      <BrandDocumentFooter />
    </div>
    <div className="rounded-3xl border border-[#dce4ef] bg-white p-5 sm:p-8" aria-labelledby="saved-forms-heading">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 id="saved-forms-heading" className="text-2xl font-semibold">Saved forms</h3><button type="button" disabled={loading || busy} onClick={() => void loadHistory(page)} className="min-h-11 rounded-xl border border-[#cbd7eb] px-4 text-sm font-semibold">Refresh status</button></div>
      {loading && <p role="status" className="mt-5 text-sm">Loading your saved forms…</p>}
      {historyError && <p role="alert" className="mt-5 text-sm text-[#9b2525]">{historyError}</p>}
      {!loading && !historyError && rows.length === 0 && <p className="mt-5 text-sm text-[#60708a]">Your submitted leave and resignation forms will be saved here.</p>}
      <div className="mt-5 space-y-4">{rows.map(item => <article key={item.id} className="min-w-0 rounded-2xl border border-[#dce4ef] p-5">
        <p className="text-xs font-semibold text-[#1f5bbd]">{item.status}</p><h4 className="mt-2 text-lg font-semibold">{item.form_type}</h4><p className="mt-2 text-xs text-[#60708a]">Submitted {date(item.created_at)} SAST</p>
        <p className="mt-3 text-sm">{item.kind === "leave" ? `${item.details.start_date} to ${item.details.end_date} · ${item.details.calendar_days} calendar day(s)` : `Proposed last teaching day: ${item.details.last_teaching_day}`}</p>
        {item.review_notes && <p className="mt-3 whitespace-pre-wrap break-words rounded-xl bg-[#f5f7fb] p-3 text-sm">Admin response: {item.review_notes}</p>}
        <details className="mt-4 text-sm"><summary className="cursor-pointer font-semibold">View submitted details</summary><dl className="mt-3 space-y-3">{[["Reason", item.details.reason], ["Handover", item.details.handover], ["Typed signature", item.details.signature_name], ["Reference", item.id]].map(([label, value]) => <div key={label}><dt className="font-semibold">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words text-[#60708a]">{value}</dd></div>)}</dl></details>
        <a href={`/api/tutor/forms/${item.id}/pdf`} className="mt-4 inline-flex min-h-11 items-center font-semibold text-[#1f5bbd] underline underline-offset-4">Download letterhead PDF</a>
      </article>)}</div>
      <div className="mt-5 flex items-center justify-between gap-3"><button type="button" disabled={page === 1 || loading || busy} onClick={() => void loadHistory(page - 1)} className="min-h-11 rounded-xl border px-4 disabled:opacity-40">Previous</button><span className="text-sm">Page {page}</span><button type="button" disabled={!more || loading || busy} onClick={() => void loadHistory(page + 1)} className="min-h-11 rounded-xl border px-4 disabled:opacity-40">Next</button></div>
    </div>
  </section>;
}
