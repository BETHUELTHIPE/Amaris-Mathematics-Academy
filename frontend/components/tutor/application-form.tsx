"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";

const input = "min-w-0 min-h-12 w-full rounded-xl border border-[#cbd6e5] bg-white px-4 py-3 text-base font-normal text-[#263852] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd]";
const labels: Record<string, string> = { full_name: "Full name", phone: "Phone", location: "Location", qualification: "Qualification", institution: "Institution", subjects: "Subjects", programmes: "Programmes", levels: "Levels", experience_years: "Experience", teaching_experience: "Teaching experience", availability: "Availability", motivation: "Motivation", consent: "Declaration", documents: "Qualifications" };

export function ApplicationForm({ name, email }: { name: string; email: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<{ field: string; message: string }[]>([]);
  const errorSummary = useRef<HTMLDivElement>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const files = data.getAll("documents").filter((file): file is File => file instanceof File && file.size > 0);
    let problems: { field: string; message: string }[] = [];
    if (!data.getAll("programmes").length) problems.push({ field: "programmes", message: "Choose at least one programme." });
    if (!files.length || files.length > 5 || files.some(file => file.size > 5 * 1024 * 1024) || files.reduce((sum, file) => sum + file.size, 0) > 15 * 1024 * 1024) problems.push({ field: "documents", message: "Attach 1–5 PDF, JPEG or PNG qualifications, up to 5 MB each and 15 MB total." });
    if (!problems.length) {
      setPending(true);
      try {
        const response = await fetch("/api/tutor-applications", { method: "POST", body: data, headers: { Accept: "application/json" } });
        const body = await response.json() as Record<string, unknown> & { application?: { reference?: string } };
        if (response.ok && body.application?.reference) { router.refresh(); return; }
        if (response.status === 401) problems = [{ field: "detail", message: "Your session expired. Sign in again in another tab, then retry this form." }];
        else problems = Object.entries(body).map(([field, message]) => ({ field, message: Array.isArray(message) ? message.join(" ") : typeof message === "string" ? message : "Check this field." }));
      } catch { problems = [{ field: "detail", message: "The service did not respond. Your entries and files are still selected. Please retry; an application received already will not be duplicated." }]; }
      setPending(false);
    }
    setErrors(problems);
    requestAnimationFrame(() => errorSummary.current?.focus());
  }
  return <form action="/api/tutor-applications" method="post" encType="multipart/form-data" onSubmit={submit} className="grid gap-8">
    <p className="text-sm leading-6 text-[#52617a]">Application email: <strong className="break-all">{email}</strong>. All fields are required. Your application will be linked to this verified account.</p>
    {errors.length > 0 && <div ref={errorSummary} tabIndex={-1} role="alert" className="rounded-xl border border-red-300 bg-red-50 p-5 text-red-900"><h2 className="font-bold">Please check your application</h2><ul className="mt-2 list-disc space-y-2 pl-5">{errors.map(({ field, message }) => <li key={field}>{labels[field] ? <a href={`#${field}`} className="underline">{labels[field]}</a> : "Application"}: {message}</li>)}</ul></div>}
    <fieldset disabled={pending} className="min-w-0 grid gap-5"><legend className="mb-5 text-xl font-semibold">1. Your details</legend>
      <Field label="Full name" name="full_name" maxLength={160} minLength={2} autoComplete="name" defaultValue={name === "Student" ? "" : name} />
      <div className="grid gap-5 sm:grid-cols-2"><Field label="Mobile number" name="phone" type="tel" autoComplete="tel" maxLength={30} pattern="\+?[0-9 ()\-]{7,30}" /><Field label="City, province and country" name="location" minLength={2} maxLength={120} autoComplete="address-level2" /></div>
    </fieldset>
    <fieldset disabled={pending} className="min-w-0 grid gap-5"><legend className="mb-5 text-xl font-semibold">2. Qualifications and teaching</legend>
      <Field label="Relevant qualification title" name="qualification" minLength={2} maxLength={200} placeholder="e.g. BSc Mathematics, teaching diploma" />
      <Field label="Awarding institution" name="institution" minLength={2} maxLength={200} />
      <Field label="Subjects you can teach" name="subjects" minLength={2} maxLength={300} placeholder="e.g. Mathematics, Mathematical Literacy, Physics" />
      <fieldset id="programmes" className="min-w-0 rounded-xl border border-[#dce4ef] p-4"><legend className="px-2 text-sm font-semibold">Programmes you can teach (choose at least one)</legend><div className="flex flex-wrap gap-5">{[["caps", "CAPS"], ["ieb", "IEB"], ["tvet", "TVET"], ["university", "University"]].map(([value, label]) => <label key={value} className="flex min-h-11 items-center gap-2 text-sm"><input name="programmes" value={value} type="checkbox" className="size-5 accent-[#1f5bbd]" />{label}</label>)}</div></fieldset>
      <Field label="Grades, levels or university modules" name="levels" minLength={2} maxLength={200} />
      <Field label="Years of teaching or tutoring experience" name="experience_years" type="number" min={0} max={80} step={1} defaultValue={0} />
      <Text label="Describe your teaching or tutoring experience" name="teaching_experience" minLength={10} maxLength={4000} />
      <Text label="Availability in South African time (UTC+2) and access to Zoom/internet" name="availability" minLength={10} maxLength={2000} />
      <Text label="Why would you like to tutor at Amaris?" name="motivation" minLength={20} maxLength={4000} />
    </fieldset>
    <fieldset disabled={pending} className="min-w-0 grid gap-4"><legend className="mb-5 text-xl font-semibold">3. Attach your qualifications</legend>
      <label htmlFor="documents" className="text-sm font-semibold">Qualification certificates or academic transcripts</label>
      <p id="file-help" className="text-sm leading-6 text-[#60708a]">Attach 1–5 PDF, JPEG or PNG files. Maximum 5 MB per file, 15 MB in total. Use scans of your relevant qualifications. Do not upload identity documents, bank details or other people’s information.</p>
      <input id="documents" name="documents" type="file" accept="application/pdf,image/jpeg,image/png" multiple required aria-describedby="file-help" className={`${input} file:mr-4 file:rounded-lg file:border-0 file:bg-[#edf3ff] file:p-2 file:text-[#0b2a5b]`} />
      <label id="consent" className="flex items-start gap-3 rounded-xl bg-[#f5f7fb] p-5 text-sm leading-6"><input type="checkbox" name="consent" value="true" required className="mt-1 size-5 shrink-0 accent-[#1f5bbd]" /><span>I confirm that this application is accurate and these are my qualifications. I have read the recruitment privacy notice below and consent to Amaris reviewing these documents and contacting me about this application.</span></label>
    </fieldset>
    <p aria-live="polite" className="text-sm text-[#52617a]">{pending ? "Submitting your application and private documents. Please keep this page open." : "Submit once. You can return here to view your reference and status."}</p>
    <button type="submit" disabled={pending} className="min-h-12 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white hover:bg-[#123d79] disabled:opacity-60">{pending ? "Submitting…" : "Submit tutor application"}</button>
  </form>;
}
function Field({ label, name, ...props }: { label: string; name: string } & React.ComponentProps<"input">) {
  return <label className="grid gap-2 text-sm font-semibold" htmlFor={name}>{label}<input {...props} id={name} name={name} required className={input} /></label>;
}
function Text({ label, name, ...props }: { label: string; name: string } & React.ComponentProps<"textarea">) {
  return <label className="grid gap-2 text-sm font-semibold" htmlFor={name}>{label}<textarea {...props} id={name} name={name} required rows={4} className={input} /></label>;
}
