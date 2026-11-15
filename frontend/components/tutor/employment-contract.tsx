"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { BriefcaseBusiness, Download, FileSignature, ShieldCheck } from "lucide-react";

type ServiceTerm = {
  service: string;
  service_label: string;
  tutor_percent: string;
  academy_percent: string;
  platform_percent?: string;
  contract_reference: string;
};
type Offer = {
  available: boolean;
  detail: string;
  terms_version?: string;
  revenue_scope?: string;
  statutory_hourly_floor?: string;
  pay_frequency?: string;
  service_terms: ServiceTerm[];
};
type SavedContract = {
  id: string;
  created_at: string;
  status: string;
  status_label: string;
  review_notes: string;
  effective_date: string | null;
  executed: boolean;
};
type ContractResponse = { offer: Offer; results: SavedContract[] };

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const formatter = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Johannesburg" });
function newKey() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function TutorEmploymentContract() {
  const [data, setData] = useState<ContractResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const key = useRef(newKey());
  const form = useRef<HTMLFormElement>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/tutor/contracts", { cache: "no-store" });
      const body = await response.json() as ContractResponse & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load the employment contract.");
      setData(body);
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Unable to load the contract." });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage(null);
    const values = new FormData(event.currentTarget);
    const payload = {
      idempotency_key: key.current,
      residential_address: String(values.get("residential_address") || ""),
      contact_phone: String(values.get("contact_phone") || ""),
      preferred_start_date: String(values.get("preferred_start_date") || ""),
      ordinary_work_days: values.getAll("ordinary_work_days").map(String),
      maximum_weekly_hours: Number(values.get("maximum_weekly_hours")),
      signature_name: String(values.get("signature_name") || ""),
      accept_employment_terms: values.get("accept_employment_terms") === "on",
      accept_privacy_notice: values.get("accept_privacy_notice") === "on",
      accept_safeguarding_duties: values.get("accept_safeguarding_duties") === "on",
      consent_electronic_signature: values.get("consent_electronic_signature") === "on",
    };
    try {
      const response = await fetch("/api/tutor/contracts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json() as SavedContract & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to sign the contract.");
      key.current = newKey();
      form.current?.reset();
      setMessage({ kind: "success", text: "Your signed contract is saved and queued for Super User review." });
      await load();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof Error ? error.message : "Submission interrupted. Retry the same details." });
    } finally { setSubmitting(false); }
  }

  return <section className="rounded-[2rem] border border-[#dce4ef] bg-white p-6 sm:p-9" aria-labelledby="tutor-employment-contract">
    <div className="flex items-start gap-4">
      <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-[#edf3ff] text-[#1f5bbd]"><BriefcaseBusiness className="size-6" /></span>
      <div>
        <p className="eyebrow">Private employment record</p>
        <h2 id="tutor-employment-contract" className="mt-2 text-2xl font-semibold">Tutor contract of employment</h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-[#60708a]">Review the employer-set remuneration and complete your written particulars. Your signed PDF is saved in your private tutor file area before the exact copy is emailed to the Super User.</p>
      </div>
    </div>

    {message && <div role={message.kind === "error" ? "alert" : "status"} className={`mt-6 rounded-xl border p-4 text-sm ${message.kind === "error" ? "border-[#f5c2bf] bg-[#fff3f3] text-[#9b2525]" : "border-[#a7ddcb] bg-[#ebfbf4] text-[#136950]"}`}>{message.text}</div>}
    {loading ? <p role="status" className="mt-6 text-sm text-[#60708a]">Loading your employment terms…</p> : data && <>
      <div className="mt-7 rounded-2xl border border-[#dce4ef] bg-[#f8faff] p-5">
        <div className="flex items-center gap-2 font-semibold text-[#0b2a5b]"><ShieldCheck className="size-5" /> Revenue split: 60% Admin / 30% Tutor / 10% Platform</div>
        {data.offer.available ? <>
          {data.offer.revenue_scope && <p className="mt-4 text-sm leading-6 text-[#263852]">{data.offer.revenue_scope}</p>}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {data.offer.service_terms.map(term => <div key={term.service} className="rounded-xl bg-white p-4 text-sm">
              <p className="font-semibold">{term.service_label}</p>
              <p className="mt-1 text-[#60708a]">Admin (Academy) {term.academy_percent}% · Tutor {term.tutor_percent}%{term.platform_percent !== undefined ? ` · Platform operating costs ${term.platform_percent}%` : ""}</p>
              <p className="mt-1 break-all text-xs text-[#60708a]">Reference {term.contract_reference}</p>
            </div>)}
          </div>
          <p className="mt-4 text-sm leading-6 text-[#263852]">For a R250 gross lesson payment, the split is R150 Admin / R75 Tutor / R25 platform operating costs, before any lawful payroll deductions. The platform allocation is not an additional deduction from the Tutor's 30% share. This revenue split does not remove employment-law protections. The Academy must meet at least <strong>R{data.offer.statutory_hourly_floor}/hour</strong>, or the later higher legal minimum. Pay frequency: {data.offer.pay_frequency}.</p>
        </> : <p role="alert" className="mt-3 text-sm text-[#9b2525]">{data.offer.detail}</p>}
      </div>

      {data.offer.available && <form ref={form} onSubmit={submit} className="mt-7 grid gap-5">
        <div className="grid gap-5 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold">Residential address
            <textarea name="residential_address" required minLength={10} maxLength={500} rows={3} autoComplete="street-address" className="rounded-xl border border-[#cbd6e5] px-4 py-3 font-normal" />
          </label>
          <label className="grid gap-2 text-sm font-semibold">Contact number
            <input name="contact_phone" required pattern="[+0-9 ()-]{7,25}" autoComplete="tel" className="rounded-xl border border-[#cbd6e5] px-4 py-3 font-normal" />
          </label>
          <label className="grid gap-2 text-sm font-semibold">Preferred commencement date
            <input name="preferred_start_date" type="date" required min={new Date().toISOString().slice(0, 10)} className="rounded-xl border border-[#cbd6e5] px-4 py-3 font-normal" />
          </label>
          <label className="grid gap-2 text-sm font-semibold">Maximum accepted hours per week
            <input name="maximum_weekly_hours" type="number" required min={1} max={45} defaultValue={20} className="rounded-xl border border-[#cbd6e5] px-4 py-3 font-normal" />
          </label>
        </div>
        <fieldset className="rounded-xl border border-[#dce4ef] p-4">
          <legend className="px-2 text-sm font-semibold">Ordinary days you can accept bookings</legend>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{days.map(day => <label key={day} className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" name="ordinary_work_days" value={day} className="size-4" />{day}</label>)}</div>
        </fieldset>
        <div className="rounded-xl border border-[#dce4ef] p-4 text-sm leading-6 text-[#263852]">
          <p className="font-semibold">Before signing</p>
          <p className="mt-2">This employment agreement covers dashboard availability, verified paid bookings, Zoom delivery, completion records, statutory pay and leave, PAYE/UIF, safeguarding, POPIA, confidentiality, materials, discipline and termination. A Super User must countersign before it becomes an executed copy.</p>
        </div>
        <label className="grid gap-2 text-sm font-semibold">Full legal name as electronic signature
          <input name="signature_name" required minLength={2} maxLength={150} autoComplete="name" className="rounded-xl border border-[#cbd6e5] px-4 py-3 font-normal" />
        </label>
        <div className="grid gap-3">
          {[
            ["accept_employment_terms", "I have reviewed and accept the employment terms and employer-configured remuneration."],
            ["accept_privacy_notice", "I acknowledge the POPIA, confidentiality and secure student-data obligations."],
            ["accept_safeguarding_duties", "I accept the professional conduct and learner-safeguarding duties."],
            ["consent_electronic_signature", "I consent to this typed name and submission being my electronic signature."],
          ].map(([name, label]) => <label key={name} className="flex items-start gap-3 text-sm leading-6"><input type="checkbox" name={name} required className="mt-1 size-4 shrink-0" />{label}</label>)}
        </div>
        <button disabled={submitting} type="submit" className="flex min-h-12 items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 font-bold text-white disabled:cursor-wait disabled:opacity-60"><FileSignature className="size-5" />{submitting ? "Saving signed contract…" : "Sign and submit contract"}</button>
      </form>}

      <div className="mt-9 border-t border-[#dce4ef] pt-7">
        <h3 className="text-xl font-semibold">Your saved contracts</h3>
        {data.results.length === 0 ? <p className="mt-3 text-sm text-[#60708a]">Your tutor-signed and executed employment contracts will be saved here.</p> : <div className="mt-4 grid gap-3">{data.results.map(item => <article key={item.id} className="rounded-xl border border-[#dce4ef] p-4 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{item.status_label}</p><p className="mt-1 text-[#60708a]">Submitted {formatter.format(new Date(item.created_at))}{item.effective_date ? ` · Effective ${item.effective_date}` : ""}</p></div><a href={`/api/tutor/contracts/${item.id}/pdf`} className="inline-flex min-h-10 items-center gap-2 rounded-full border border-[#cbd6e5] px-4 font-semibold text-[#1f5bbd]"><Download className="size-4" />{item.executed ? "Download executed PDF" : "Download signed PDF"}</a></div>
          {item.review_notes && <p className="mt-3 rounded-lg bg-[#f5f7fb] p-3 text-[#263852]">Admin note: {item.review_notes}</p>}
        </article>)}</div>}
      </div>
    </>}
  </section>;
}
