"use client";

import { useState, type FormEvent } from "react";
import type { TutorVideo, TutorVideoLibrary } from "@/lib/tutor-api";
import { sendS3, sendVimeo } from "./video-upload-transport";

type Destination = TutorVideo["provider"];
const names: Record<Destination, string> = { s3: "Private AWS S3", vimeo: "Vimeo" };
type Ticket = { submission: string; ticket: string; url: string; headers?: Record<string, string> };

async function uploadRequest<T>(body: Record<string, unknown>): Promise<T> {
  const response = await fetch("/api/tutor-videos", {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === "string" ? detail : "The video could not be submitted.");
  }
  return data as T;
}

export function TutorLessonVideos({ library }: { library: TutorVideoLibrary }) {
  const [videos, setVideos] = useState(library.videos);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const available = (Object.keys(names) as Destination[]).filter((key) => library.providers[key]);
  const [provider, setProvider] = useState<Destination>(available[0] ?? "s3");
  const [prepared, setPrepared] = useState<Ticket | null>(null);
  const [transferred, setTransferred] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  function resetUpload() {
    setPrepared(null);
    setTransferred(false);
    setProgress(null);
    setError("");
    setNotice("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !file || !title.trim() || !library.providers[provider]) return;
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const ticket = prepared ?? await uploadRequest<Ticket>({
        action: "start", provider, filename: file.name, size: file.size, title: title.trim(),
      });
      setPrepared(ticket);
      if (!transferred) {
        setProgress(0);
        try {
          const progressUpload = (fraction: number) => setProgress(Math.round(fraction * 100));
          if (provider === "s3") await sendS3(ticket.url, ticket.headers ?? {}, file, progressUpload);
          else await sendVimeo(ticket.url, file, progressUpload);
        } catch (error) {
          if (provider === "s3") setPrepared(null);
          throw error;
        }
        setTransferred(true);
        setProgress(100);
      }
      const video = await uploadRequest<TutorVideo>({
        action: "finish", provider, submission: ticket.submission, ticket: ticket.ticket,
      });
      setVideos((current) => [video, ...current.filter((item) => item.id !== video.id)].slice(0, 25));
      setTitle("");
      setFile(null);
      form.reset();
      resetUpload();
      setNotice("Lesson video submitted for review.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "The connection was interrupted. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 block w-full min-w-0 rounded-lg border border-[#b9c9df] bg-white px-3 py-2.5";
  return (
    <section id="lesson-videos" aria-labelledby="lesson-videos-title" className="rounded-[2rem] border border-[#dce4ef] bg-white p-5 sm:p-9">
      <h2 id="lesson-videos-title" className="text-2xl font-semibold">Lesson videos</h2>
      <p className="mt-2 text-sm text-[#53647b]">Upload a lesson recording for the academy to review and link to a course.</p>
      {available.length ? (
        <form onSubmit={submit} className="mt-5 space-y-4">
          <fieldset disabled={busy} className="grid min-w-0 gap-4 sm:grid-cols-2">
            <label className="block min-w-0 text-sm font-semibold">Lesson title
              <input className={field} maxLength={180} required value={title}
                onChange={(event) => { setTitle(event.target.value); resetUpload(); }} />
            </label>
            <label className="block min-w-0 text-sm font-semibold">Upload destination
              <select className={field} value={provider}
                onChange={(event) => { setProvider(event.target.value as Destination); resetUpload(); }}>
                {available.map((item) => <option key={item} value={item}>{names[item]}</option>)}
              </select>
            </label>
            <label className="block min-w-0 text-sm font-semibold sm:col-span-2">Video file
              <input className={field} type="file" accept="video/*,.mkv,.mxf,.m4v" required
                onChange={(event) => { setFile(event.target.files?.[0] ?? null); resetUpload(); }} />
            </label>
          </fieldset>
          <p className="text-sm text-[#53647b]">{provider === "s3" ? "MP4, M4V or WebM." : "Select a Vimeo-supported video format."} Maximum 4 GiB.</p>
          {progress !== null && <progress aria-label="Upload progress" className="w-full" max={100} value={progress} />}
          {notice && <p role="status" className="text-sm text-[#136950]">{notice}</p>}
          {error && <p role="alert" className="text-sm text-[#9b2525]">{error}</p>}
          <button disabled={busy} type="submit" className="min-h-12 rounded-full bg-[#0b2a5b] px-6 font-semibold text-white disabled:opacity-60">
            {busy ? "Submitting…" : transferred ? "Retry submission" : "Upload for review"}
          </button>
        </form>
      ) : <p role="status" className="mt-5 text-sm text-[#53647b]">Video uploads are temporarily unavailable.</p>}
      {videos.length > 0 && (
        <div className="mt-7 border-t border-[#dce4ef] pt-5">
          <h3 className="font-semibold">Your recent submissions</h3>
          <ul className="mt-3 divide-y divide-[#dce4ef]">
            {videos.map((video) => <li key={video.id} className="flex min-w-0 flex-wrap items-start justify-between gap-x-5 gap-y-1 py-3 text-sm">
              <span className="min-w-0 break-words [overflow-wrap:anywhere]">{video.title} · {names[video.provider]}</span>
              <span className="text-[#53647b]">{video.ready ? "Published" : "Awaiting review"}</span>
            </li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
