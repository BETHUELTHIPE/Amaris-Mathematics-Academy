"use client";

import { LocationFields } from "@/components/site/location-fields";
import type { InitialLocation } from "@/lib/location-data";
import { useActionState, useState, type FormEvent } from "react";
import { useFormStatus } from "react-dom";
import { CheckCircle2, LoaderCircle, Send } from "lucide-react";
import { submitEnquiry } from "@/app/contact/actions";
import { initialEnquiryState } from "@/app/contact/state";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Button } from "@/components/ui/button";
import { academyBrand } from "@/lib/brand";
import { ClearSafeFormDraft, SafeFormDraft } from "@/components/site/safe-form-draft";
import { contactRequiredErrors, contactRequiredMessages, type ContactField } from "@/lib/contact-validation";

const contactDraftFields = ["fullName", "email", "phone", "enquiryType", "message"];

function FieldError({ field, message }: { field: ContactField; message?: string }) {
  return message ? <p id={`${field}-error`} className="mt-2 text-sm font-medium text-[#b42318]" role="alert">{message}</p> : null;
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return <Button type="submit" disabled={pending} className="h-12 rounded-full bg-[#0b2a5b] px-7 text-base font-bold text-white hover:bg-[#133b76]">{pending ? <><LoaderCircle className="size-4 animate-spin" />Sending enquiry…</> : <>Send enquiry <Send className="size-4" /></>}</Button>;
}

export function EnquiryForm({ location }: { location: InitialLocation }) {
  const [state, formAction] = useActionState(submitEnquiry, initialEnquiryState);
  const [clientErrors, setClientErrors] = useState<Partial<Record<ContactField | "provinceOther" | "cityOther", string>>>({});
  const [editedFields, setEditedFields] = useState<Set<string>>(new Set());
  const errors = Object.fromEntries(([...Object.keys(contactRequiredMessages), "provinceOther", "cityOther"] as (ContactField | "provinceOther" | "cityOther")[]).map((field) => [
    field, clientErrors[field] ?? (editedFields.has(field) ? undefined : state.errors?.[field]),
  ]));

  function handleInvalid(event: FormEvent<HTMLFormElement>) {
    const control = event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
    const field = control.name as ContactField;
    if (!(field in contactRequiredMessages)) return;
    let message: string = contactRequiredMessages[field];
    if (!control.validity.valueMissing && control.value.trim()) {
      if (field === "email") message = "Please enter a valid email address.";
      else if (field === "message") message = "Please enter at least 20 characters in your message.";
    }
    control.setCustomValidity(message);
    setClientErrors((previous) => ({ ...previous, [field]: message }));
  }

  function handleInput(event: FormEvent<HTMLFormElement>) {
    const control = event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
    const field = control.name as ContactField | "provinceOther" | "cityOther";
    if (!Object.hasOwn(contactRequiredMessages, field) && field !== "provinceOther" && field !== "cityOther") return;
    control.setCustomValidity("");
    setClientErrors((previous) => ({ ...previous, [field]: undefined }));
    setEditedFields((previous) => new Set([...previous, field]));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    const requiredErrors = contactRequiredErrors(Object.fromEntries(new FormData(event.currentTarget).entries()));
    setClientErrors(requiredErrors);
    if (Object.keys(requiredErrors).length) {
      event.preventDefault();
      const field = Object.keys(requiredErrors)[0];
      event.currentTarget.querySelector<HTMLElement>(`[name="${field}"]`)?.focus();
      return;
    }
    setEditedFields(new Set());
  }

  if (state.status === "success") {
    return <><ClearSafeFormDraft draftKey="contact-enquiry-v1" /><div className="mt-8 overflow-hidden rounded-2xl border border-[#a6d7be] bg-white" role="status"><div className="flex items-center gap-3 border-b border-[#dce4ef] bg-[#f6f8fc] px-5 py-4">{/* Static brand asset: direct delivery avoids loading the Next/Vinext image runtime for the enquiry form. */}<img src={academyBrand.logoPath} alt="Amaris Mathematics Academy logo" width={48} height={48} className="size-12 object-contain" /><div><p className="font-bold text-[#07152d]">{academyBrand.name}</p><p className="text-xs text-[#60708a]">{academyBrand.phoneDisplay} · {academyBrand.email}</p></div></div><div className="p-6"><CheckCircle2 className="size-8 text-[#147a4b]" /><h3 className="mt-4 text-xl font-semibold text-[#0a4d30]">Enquiry received</h3><p className="mt-2 text-base leading-7 text-[#396554]">{state.message}</p><p className="mt-4 text-sm text-[#557365]">For urgent support, call <a href={academyBrand.phoneHref} className="font-semibold underline">{academyBrand.phoneDisplay}</a>.</p><p className="mt-5 border-t border-[#dce4ef] pt-4 text-xs leading-5 text-[#60708a]">{academyBrand.address} · {academyBrand.website}</p></div></div></>;
  }

  return (
    <form action={formAction} onInvalidCapture={handleInvalid} onInputCapture={handleInput} onChangeCapture={handleInput} onSubmit={handleSubmit} className="mt-8 space-y-6">
      <SafeFormDraft draftKey="contact-enquiry-v1" allowedFields={contactDraftFields} />
      <div className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
        <label htmlFor="website">Website</label><input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
      </div>
      {state.message && <div className="rounded-xl border border-[#f0b6b0] bg-[#fff3f1] px-4 py-3 text-sm font-medium text-[#8f2d24]" role="alert">{state.message}</div>}
      <div className="grid gap-6 sm:grid-cols-2">
        <div><label htmlFor="fullName" className="text-sm font-semibold text-[#263951]">Full name <span className="text-[#b42318]">*</span></label><Input id="fullName" name="fullName" type="text" required minLength={2} maxLength={80} autoComplete="name" aria-invalid={Boolean(errors.fullName)} aria-describedby={errors.fullName ? "fullName-error" : undefined} className="mt-2 h-12 rounded-xl border-[#cdd8e6] bg-[#fbfcfe] px-4 text-base" placeholder="Your full name" /><FieldError field="fullName" message={errors.fullName} /></div>
        <div><label htmlFor="email" className="text-sm font-semibold text-[#263951]">Email address <span className="text-[#b42318]">*</span></label><Input id="email" name="email" type="email" required maxLength={160} autoComplete="email" aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? "email-error" : undefined} className="mt-2 h-12 rounded-xl border-[#cdd8e6] bg-[#fbfcfe] px-4 text-base" placeholder="name@example.com" /><FieldError field="email" message={errors.email} /></div>
        <div><label htmlFor="phone" className="text-sm font-semibold text-[#263951]">Phone number <span className="text-[#b42318]">*</span></label><Input id="phone" name="phone" type="tel" required maxLength={30} autoComplete="tel" aria-invalid={Boolean(errors.phone)} aria-describedby={errors.phone ? "phone-error" : undefined} className="mt-2 h-12 rounded-xl border-[#cdd8e6] bg-[#fbfcfe] px-4 text-base" placeholder="e.g. 071 234 5678" /><FieldError field="phone" message={errors.phone} /></div>
        <div><label htmlFor="enquiryType" className="text-sm font-semibold text-[#263951]">Enquiry type <span className="text-[#b42318]">*</span></label><NativeSelect id="enquiryType" name="enquiryType" required defaultValue="" aria-invalid={Boolean(errors.enquiryType)} aria-describedby={errors.enquiryType ? "enquiryType-error" : undefined} className="mt-2 h-12 w-full rounded-xl border-[#cdd8e6] bg-[#fbfcfe] px-4 text-base"><NativeSelectOption value="" disabled>Select a topic</NativeSelectOption><NativeSelectOption value="course-guidance">Course guidance</NativeSelectOption><NativeSelectOption value="registration">Registration</NativeSelectOption><NativeSelectOption value="payments">Payments</NativeSelectOption><NativeSelectOption value="student-account">Student account</NativeSelectOption><NativeSelectOption value="technical-support">Technical support</NativeSelectOption><NativeSelectOption value="other">Other enquiry</NativeSelectOption></NativeSelect><FieldError field="enquiryType" message={errors.enquiryType} /></div>
      </div>
      <LocationFields initial={location} draftKey="contact-enquiry-v1" returnTo="/contact" errors={errors} />
      <div><div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1"><label htmlFor="message" className="text-sm font-semibold text-[#263951]">How can we help? <span className="text-[#b42318]">*</span></label><span className="text-xs text-[#60708a]">20–2,000 characters</span></div><Textarea id="message" name="message" required minLength={20} maxLength={2000} aria-invalid={Boolean(errors.message)} aria-describedby={errors.message ? "message-error" : undefined} className="mt-2 min-h-40 resize-y rounded-xl border-[#cdd8e6] bg-[#fbfcfe] p-4 text-base leading-7" placeholder="Tell us what you need help with, including your study level or order reference when relevant." /><FieldError field="message" message={errors.message} /></div>
      <div><div className="flex items-start gap-3 text-sm leading-6 text-[#60708a]"><input id="consent" name="consent" type="checkbox" required value="on" aria-labelledby="consent-label" aria-invalid={Boolean(errors.consent)} aria-describedby={errors.consent ? "consent-error" : undefined} className="mt-0.5 size-6 shrink-0 cursor-pointer rounded border border-[#9aabc0] accent-[#1f5bbd]" /><span id="consent-label">I agree that Amaris Mathematics Academy may use these details to respond to my enquiry. <span className="text-[#b42318]">*</span></span></div><FieldError field="consent" message={errors.consent} /></div>
      <div className="flex flex-col gap-4 border-t border-[#e4eaf2] pt-6 sm:flex-row sm:items-center sm:justify-between"><SubmitButton /><p className="text-sm text-[#60708a]">Prefer to speak? <a href={academyBrand.phoneHref} className="font-semibold text-[#1f5bbd] hover:underline">Call {academyBrand.phoneDisplay}</a></p></div>
    </form>
  );
}
