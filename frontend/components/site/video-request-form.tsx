"use client";

import { useState, type FormEvent } from "react";
import { CreditCard, FileUp, LoaderCircle, ShieldCheck } from "lucide-react";
import type { VideoRequestCheckoutSession } from "@/lib/student-api";
import type { VideoRequestPackage } from "@/lib/video-requests";
import { uploadStudentDocument, type SignedStudentUpload } from "@/lib/supabase/resumable-upload";

const programmes = [
  ["caps", "CAPS"],
  ["ieb", "IEB"],
  ["tvet", "TVET"],
  ["university", "University"],
] as const;
const MAX_DOCUMENT_BYTES = 1024 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/pdf", "image/jpeg", "image/png"]);
const subjects = [
  ["mathematics", "Mathematics"],
  ["mathematical_literacy", "Mathematical Literacy"],
] as const;

export function VideoRequestForm({ packages }: { packages: VideoRequestPackage[] }) {
  const [checkout, setCheckout] = useState<VideoRequestCheckoutSession | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setCheckout(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("idempotency_key", `video-${crypto.randomUUID().replaceAll("-", "")}`);
    const files = data.getAll("documents").filter((value): value is File => value instanceof File && value.size > 0);
    data.delete("documents");

    try {
      if (files.length > 5 || files.some((file) => !ALLOWED_TYPES.has(file.type)
          || file.size > MAX_DOCUMENT_BYTES)
          || files.reduce((total, file) => total + file.size, 0) > MAX_DOCUMENT_BYTES) {
        throw new Error("Choose up to five PDF, JPEG or PNG documents, totalling no more than 1 GB.");
      }
      setUploadProgress("");
      // Create a pending, server-priced checkout without sending file bytes through Render.
      const response = await fetch("/api/video-requests/checkout", {
        method: "POST",
        body: data,
        headers: { Accept: "application/json" },
      });
      const body = (await response.json()) as VideoRequestCheckoutSession | { detail?: string };
      if (!response.ok || !("request_reference" in body)) {
        throw new Error("detail" in body && body.detail ? body.detail : "Video request failed.");
      }
      for (const [index, file] of files.entries()) {
        setUploadProgress("Preparing document " + (index + 1) + " of " + files.length);
        const signedResponse = await fetch("/api/video-requests/upload-session", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            request_reference: body.request_reference,
            content_type: file.type,
            size_bytes: file.size,
          }),
        });
        if (!signedResponse.ok) {
          throw new Error("Could not authorize upload. Confirm the Supabase bucket supports 1 GB.");
        }
        const signed = (await signedResponse.json()) as SignedStudentUpload;
        await uploadStudentDocument(file, signed, (percentage) => {
          setUploadProgress("Uploading document " + (index + 1) + " of " + files.length
            + " (" + percentage + "%)");
        });
        const verify = await fetch("/api/video-requests/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            request_reference: body.request_reference,
            storage_path: signed.path,
            original_name: file.name,
            content_type: file.type,
            size_bytes: file.size,
          }),
        });
        if (!verify.ok) {
          throw new Error("The uploaded document could not be verified. Payment has not started.");
        }
      }
      setUploadProgress("");
      setCheckout(body);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "We could not create the video request.");
    } finally {
      setSubmitting(false);
      setUploadProgress("");
    }
  }

  if (checkout) {
    return (
      <section className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.08)] sm:p-9" aria-live="polite">
        <p className="eyebrow">Secure checkout</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-[-.035em]">Confirm your requested video</h2>
        <dl className="mt-6 grid gap-3 rounded-2xl bg-[#f7f9fc] p-5 text-sm">
          <div><dt className="font-semibold">Package</dt><dd className="mt-1 text-[#60708a]">{checkout.request.request_type}</dd></div>
          <div><dt className="font-semibold">Topic</dt><dd className="mt-1 text-[#60708a]">{checkout.request.topic}</dd></div>
          <div><dt className="font-semibold">Programme</dt><dd className="mt-1 text-[#60708a]">{checkout.request.programme} · {checkout.request.subject} · {checkout.request.level}</dd></div>
          <div><dt className="font-semibold">Amount</dt><dd className="mt-1 text-xl font-bold text-[#0b2a5b]">R{checkout.request.amount}</dd></div>
          <div><dt className="font-semibold">Reference</dt><dd className="mt-1 break-all font-mono text-[#60708a]">{checkout.request_reference}</dd></div>
        </dl>
        <p className="mt-5 text-sm leading-7 text-[#60708a]">
          Your ticket enters the recording queue only after PayFast verifies the payment on the server.
        </p>
        <form method="post" action={checkout.gateway_url} className="mt-6">
          {Object.entries(checkout.fields).map(([name, value]) => (
            <input key={name} type="hidden" name={name} value={value} />
          ))}
          <button type="submit" className="flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white">
            <CreditCard className="size-4" /> Continue to PayFast
          </button>
        </form>
        <button type="button" onClick={() => setCheckout(null)} className="mt-3 min-h-11 w-full rounded-full border border-[#b7c5d8] px-5 font-semibold text-[#0b2a5b]">
          Change request details
        </button>
      </section>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-[2rem] border border-[#dce4ef] bg-white p-7 shadow-[0_25px_75px_rgba(7,21,45,.08)] sm:p-9">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="grid gap-2 text-sm font-semibold">
          Programme
          <select name="programme" required defaultValue="" className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
            <option value="">Choose programme</option>
            {programmes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Subject
          <select name="subject" required defaultValue="" className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
            <option value="">Choose subject</option>
            {subjects.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Grade or academic level
          <input name="level" required minLength={1} maxLength={80} placeholder="e.g. Grade 12 or UNISA first year" className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal" />
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Video package
          <select name="request_type" required defaultValue="" className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
            <option value="">Choose package</option>
            {packages.map((item) => <option key={item.value} value={item.value}>{item.label} — R{item.amount}</option>)}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-semibold sm:col-span-2">
          Topic, chapter, assignment or exam
          <input name="topic" required minLength={2} maxLength={180} placeholder="e.g. Grade 12 differential calculus, November 2025 Question 4" className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal" />
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Preferred duration
          <select name="preferred_duration_minutes" defaultValue="60" className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal">
            {[30, 45, 60, 90, 120, 180].map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-semibold">
          Explanation style
          <input name="explanation_style" maxLength={120} placeholder="e.g. Slow steps with exam tips" className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal" />
        </label>
        <label className="grid gap-2 text-sm font-semibold sm:col-span-2">
          Instructions
          <textarea name="instructions" maxLength={2000} rows={5} placeholder="Tell the tutor which questions or methods need the most attention." className="rounded-xl border border-[#c9d5e5] px-4 py-3 font-normal" />
        </label>
        <label className="grid gap-2 text-sm font-semibold sm:col-span-2">
          Supporting documents (optional)
          <span className="rounded-2xl border border-dashed border-[#aac3ec] bg-[#f8fbff] p-5">
            <span className="flex items-center gap-2"><FileUp className="size-5 text-[#1f5bbd]" />Upload up to five PDF, JPEG or PNG documents</span>
            <input name="documents" type="file" multiple accept="application/pdf,image/jpeg,image/png" className="mt-3 block w-full text-sm font-normal" />
            <span className="mt-2 block text-xs font-normal text-[#60708a]">Up to 1 GB per file and 1 GB total. Large files upload directly to private Supabase storage and can resume after a temporary interruption.</span>
          </span>
        </label>
      </div>

      {uploadProgress && <p role="status" aria-live="polite" className="mt-5 text-sm text-[#0b2a5b]">{uploadProgress}</p>}
      {error && <div role="alert" className="mt-5 rounded-xl border border-[#e7a5ab] bg-[#fff1f2] p-4 text-sm text-[#9f2330]">{error}</div>}

      <button disabled={submitting} type="submit" className="mt-7 flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white disabled:cursor-wait disabled:opacity-70">
        {submitting ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
        {submitting ? "Preparing your documents…" : "Review secure payment"}
      </button>
      <p className="mt-4 text-center text-xs leading-6 text-[#60708a]">Server-priced · private documents · verified payment required · student-only delivery</p>
    </form>
  );
}

