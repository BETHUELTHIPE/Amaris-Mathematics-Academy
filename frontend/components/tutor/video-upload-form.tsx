"use client";

import { useRef, useState } from "react";

export function TutorVideoUploadForm({ maxBytes }: { maxBytes: number }) {
  const key = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const inputClass = "mt-2 min-h-12 w-full rounded-xl border border-[#c9d5e5] bg-white px-4 text-[#263852]";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("source_file");
    setError(""); setMessage("");
    if (!(file instanceof File) || !file.size || file.size > maxBytes) {
      setError(`Choose a video up to ${Math.floor(maxBytes / 1048576)} MiB.`); return;
    }
    key.current ||= crypto.randomUUID();
    data.set("idempotency_key", key.current);
    const minutes = Number(data.get("duration_minutes") || 0);
    data.set("duration_seconds", String(Math.round(minutes * 60)));
    data.delete("duration_minutes");
    setBusy(true);
    try {
      const result = await fetch("/api/tutor/videos", { method: "POST", body: data, cache: "no-store" });
      const body = await result.json().catch(() => ({})) as { detail?: string; activity_reference?: string };
      if (!result.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Check the video details and try again.");
        if ([400, 409, 413, 415].includes(result.status)) key.current = null;
        return;
      }
      setMessage(`Video received for Admin review. Reference: ${body.activity_reference || "saved"}.`);
      form.reset(); key.current = null;
    } catch {
      setError("The connection was interrupted. Retry the same video and details to check your submission safely.");
    } finally { setBusy(false); }
  }

  return <section aria-labelledby="tutor-video-title" className="rounded-[2rem] border border-[#dce4ef] bg-white p-6 sm:p-9">
    <p className="eyebrow">Share your teaching</p><h2 id="tutor-video-title" className="mt-2 text-2xl font-semibold">Submit a lesson video</h2>
    <p className="mt-3 text-sm leading-7 text-[#60708a]">Add your video and teaching details. Your submission stays private while the academy reviews it. Admin receives a detailed activity alert.</p>
    <form onSubmit={submit} className="mt-6 grid gap-5" aria-busy={busy}>
      <fieldset disabled={busy} className="grid min-w-0 gap-5 sm:grid-cols-2">
        <legend className="sr-only">Video and learning details</legend>
        <label className="font-semibold sm:col-span-2">Video title<input name="title" required minLength={2} maxLength={180} className={inputClass} /></label>
        <label className="font-semibold">Curriculum<select aria-label="Curriculum" name="curriculum" required defaultValue="" className={inputClass}><option value="" disabled>Choose curriculum</option><option value="caps">CAPS</option><option value="ieb">IEB</option><option value="nated">TVET NATED</option><option value="ncv">TVET NC(V)</option><option value="university">University / UNISA</option></select></label>
        <label className="font-semibold">Subject<select aria-label="Subject" name="subject" required defaultValue="" className={inputClass}><option value="" disabled>Choose subject</option><option value="mathematics">Mathematics</option><option value="mathematical_literacy">Mathematical Literacy</option></select></label>
        <label className="font-semibold">Grade, level or module<input name="academic_level" required maxLength={100} placeholder="For example: Grade 11 or MAT1503" className={inputClass} /></label>
        <label className="font-semibold">Topic<input name="topic" required minLength={2} maxLength={180} className={inputClass} /></label>
        <label className="font-semibold">Duration in minutes (optional)<input name="duration_minutes" type="number" min={1} max={1440} step={1} className={inputClass} /></label>
        <label className="min-w-0 font-semibold sm:col-span-2">Lesson video<input aria-label="Lesson video" aria-describedby="tutor-video-file-help" name="source_file" required type="file" accept=".mp4,.m4v,.webm,.mov" className="mt-2 block w-full min-w-0 rounded-xl border border-[#c9d5e5] p-3 text-sm" /><span id="tutor-video-file-help" className="mt-2 block text-xs font-normal text-[#60708a]">MP4, M4V, WebM or MOV, up to {Math.floor(maxBytes / 1048576)} MiB. Keep this page open until the upload is confirmed.</span></label>
      </fieldset>
      {error && <p role="alert" className="rounded-xl bg-[#fff3f3] p-4 text-sm text-[#9b2525]">{error}</p>}
      {message && <p role="status" className="rounded-xl bg-[#ebfbf4] p-4 text-sm text-[#136950]">{message}</p>}
      <button disabled={busy} type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-bold text-white disabled:opacity-60">{busy ? "Uploading your video…" : "Submit video for review"}</button>
    </form>
  </section>;
}
