"use client";

import { useState, type FormEvent } from "react";
import { CreditCard, FileUp, LoaderCircle, ShieldCheck } from "lucide-react";
import type { VideoRequestCheckoutSession } from "@/lib/student-api";
import type { VideoRequestPackage } from "@/lib/video-requests";
import { uploadVideoRequestFiles, VIDEO_UPLOAD_LIMIT_BYTES, VIDEO_UPLOAD_MAX_FILES } from "@/lib/video-upload";

const programmes = [
  ["caps", "CAPS"],
  ["ieb", "IEB"],
  ["tvet", "TVET"],
  ["university", "University"],
] as const;
const subjects = [
  ["mathematics", "Mathematics"],
  ["mathematical_literacy", "Mathematical Literacy"],
] as const;

export function VideoRequestForm({ packages }: { packages: VideoRequestPackage[] }) {
  const [checkout, setCheckout] = useState<VideoRequestCheckoutSession | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setCheckout(null);
    setUploadPercent(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    data.set("idempotency_key", `video-${crypto.randomUUID().replaceAll("-", "")}`);
    const files = [...data.getAll("documents"), ...data.getAll("folder")]
      .filter((value): value is File => value instanceof File && value.size > 0);
    data.delete("documents");
    data.delete("folder");
    if (files.length > VIDEO_UPLOAD_MAX_FILES ||
        files.reduce((total, file) => total + file.size, 0) > VIDEO_UPLOAD_LIMIT_BYTES) {
      setError("Upload no more than 200 files or 1 GiB total per request.");
      setSubmitting(false);
      return;
    }

    try {
      const response = await fetch("/api/video-requests/checkout", {
        method: "POST",
        body: data,
        headers: { Accept: "application/json" },
      });
      const body = (await response.json()) as VideoRequestCheckoutSession | { detail?: string };
      if (!response.ok || !("request_reference" in body)) {
        throw new Error("detail" in body && body.detail ? body.detail : "Video request failed.");
      }
      if (files.length > 0) {
        setUploadPercent(0);
        await uploadVideoRequestFiles(body.request_reference, files, setUploadPercent);
      }
      setCheckout(body);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "We could not create the video request.");
    } finally {
      setSubmitting(false);
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
          Supporting files or a folder (optional)
          <span className="rounded-2xl border border-dashed border-[#aac3ec] bg-[#f8fbff] p-5">
            <span className="flex items-center gap-2"><FileUp className="size-5 text-[#1f5bbd]" />Upload images, PDF, Office documents, ZIP, text or study videos</span>
            <span className="mt-3 block text-xs text-[#60708a]">Select individual files:</span>
            <input name="documents" type="file" multiple
              accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.txt,.csv,.docx,.xlsx,.pptx,.zip,.mp4,.webm"
              className="mt-1 block w-full text-sm font-normal" />
            <span className="mt-4 block text-xs text-[#60708a]">Or select a complete folder (supported browsers):</span>
            <input name="folder" type="file" multiple
              ref={(node) => { if (node) node.setAttribute("webkitdirectory", ""); }}
              className="mt-1 block w-full text-sm font-normal" />
            <span className="mt-3 block text-xs font-normal text-[#60708a]">
              Up to 200 files and 1 GiB combined. Folder paths are retained for your tutor.
              Files transfer in 8 MB parts directly to private storage. Uploads must finish before payment.
            </span>
          </span>
        </label>
      </div>

      {uploadPercent !== null && submitting && (
        <div className="mt-5" role="status" aria-live="polite">
          <p className="text-sm font-medium">Uploading supporting files: {uploadPercent}%</p>
          <progress aria-label="Upload progress" className="mt-2 w-full" value={uploadPercent} max={100} />
        </div>
      )}
      {error && <div role="alert" className="mt-5 rounded-xl border border-[#e7a5ab] bg-[#fff1f2] p-4 text-sm text-[#9f2330]">{error}</div>}

      <button disabled={submitting} type="submit" className="mt-7 flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-[#0b2a5b] px-6 py-3 font-bold text-white disabled:cursor-wait disabled:opacity-70">
        {submitting ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
        {submitting ? (uploadPercent === null ? "Securing request…" : `Uploading ${uploadPercent}%…`) : "Review secure payment"}
      </button>
      <p className="mt-4 text-center text-xs leading-6 text-[#60708a]">Server-priced · private documents · verified payment required · student-only delivery</p>
    </form>
  );
}

