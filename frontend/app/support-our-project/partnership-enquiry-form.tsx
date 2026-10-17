"use client";

import { useActionState } from "react";
import { submitPartnershipEnquiry } from "@/app/support-our-project/actions";
import { initialEnquiryState } from "@/app/contact/state";

const fieldClass = "mt-2 w-full rounded-xl border border-[#c5d1e1] bg-white px-4 py-3 text-[#07152d] outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd]";
const labelClass = "block text-sm font-semibold text-[#07152d]";

export function PartnershipEnquiryForm() {
  const [state, action, pending] = useActionState(submitPartnershipEnquiry, initialEnquiryState);

  return (
    <form action={action} className="mt-8 space-y-5" aria-label="Investor and partnership enquiry">
      <div className="hidden" aria-hidden="true">
        <label htmlFor="partnership-website">Website</label>
        <input id="partnership-website" name="website" tabIndex={-1} autoComplete="off" />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        {[
          { name: "fullName", label: "Contact person's full name", autoComplete: "name" },
          { name: "email", label: "Business email address", type: "email", autoComplete: "email" },
          { name: "organisation", label: "Company / organisation (or Individual)", autoComplete: "organization" },
          { name: "role", label: "Job title / role", autoComplete: "organization-title" },
          { name: "phone", label: "Phone (optional)", type: "tel", autoComplete: "tel", optional: true },
        ].map((field) => (
          <div key={field.name}>
            <label htmlFor={`partner-${field.name}`} className={labelClass}>{field.label}{!field.optional && " *"}</label>
            <input id={`partner-${field.name}`} name={field.name} type={field.type ?? "text"} autoComplete={field.autoComplete} required={!field.optional} className={fieldClass} aria-invalid={Boolean(state.errors?.[field.name])} aria-describedby={state.errors?.[field.name] ? `partner-${field.name}-error` : undefined} />
            {state.errors?.[field.name] && <p id={`partner-${field.name}-error`} className="mt-1 text-sm text-red-700">{state.errors[field.name]}</p>}
          </div>
        ))}
        <div>
          <label htmlFor="partner-interest" className={labelClass}>Type of opportunity *</label>
          <select id="partner-interest" name="interest" required defaultValue="" className={fieldClass} aria-invalid={Boolean(state.errors?.interest)}>
            <option value="" disabled>Select an opportunity</option>
            <option value="investment">Investment / funding proposal</option>
            <option value="sponsorship">Education sponsorship</option>
            <option value="strategic-partnership">Strategic / corporate partnership</option>
            <option value="technology-partnership">Technology / infrastructure partnership</option>
            <option value="other">Other project support</option>
          </select>
          {state.errors?.interest && <p className="mt-1 text-sm text-red-700">{state.errors.interest}</p>}
        </div>
      </div>
      <div>
        <label htmlFor="partner-message" className={labelClass}>Tell us about your proposal and what you would like to discuss *</label>
        <textarea id="partner-message" name="message" rows={6} minLength={30} maxLength={1500} required className={fieldClass} aria-invalid={Boolean(state.errors?.message)} aria-describedby="partner-message-help" placeholder="Introduce your organisation, proposed investment or collaboration, expected outcomes and preferred next steps." />
        <p id="partner-message-help" className="mt-1 text-sm text-[#526781]">Please do not submit banking credentials, passwords, or confidential financial documents here.</p>
        {state.errors?.message && <p className="mt-1 text-sm text-red-700">{state.errors.message}</p>}
      </div>
      <label className="flex items-start gap-3 text-sm text-[#526781]">
        <input name="consent" type="checkbox" required className="mt-1 size-4" />
        I consent to Amaris using my contact details to respond to this partnership enquiry. *
      </label>
      {state.errors?.consent && <p className="text-sm text-red-700">{state.errors.consent}</p>}
      {state.message && <p role={state.status === "error" ? "alert" : "status"} aria-live="polite" className={`rounded-xl p-4 text-sm ${state.status === "success" ? "bg-green-50 text-green-900" : "bg-red-50 text-red-900"}`}>{state.message}</p>}
      <button type="submit" disabled={pending} className="min-h-12 rounded-full bg-[#0b2a5b] px-7 py-3 font-semibold text-white transition hover:bg-[#1f5bbd] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#1f5bbd] disabled:opacity-60">
        {pending ? "Sending proposal…" : "Submit partnership enquiry"}
      </button>
    </form>
  );
}
