"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, FileText, ShieldCheck, Upload } from "lucide-react";
import type { CustomVideoOptions } from "@/lib/custom-videos";

type Props = {
  options: CustomVideoOptions;
};

const acceptedExtensions = [
  ".pdf",
  ".jpg",
  ".jpeg",
  ".png",
  ".heic",
  ".heif",
  ".doc",
  ".docx",
  ".ppt",
  ".pptx",
  ".xls",
  ".xlsx",
  ".txt",
];

export function CustomVideoRequestWizard({ options }: Props) {
  const [step, setStep] = useState(1);
  const [curriculum, setCurriculum] = useState("");
  const [subject, setSubject] = useState("");
  const [grade, setGrade] = useState("");
  const [topic, setTopic] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [requestKey, setRequestKey] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setRequestKey(`video-${crypto.randomUUID().replaceAll("-", "")}`.slice(0, 64));
  }, []);

  const amount = useMemo(() => {
    if (!options.amount) return "Price not configured";
    return new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: options.currency || "ZAR",
    }).format(Number(options.amount));
  }, [options.amount, options.currency]);

  const canContinueAcademic =
    Boolean(curriculum && subject && grade) && topic.trim().length >= 2;

  function validateFiles(selected: File[]) {
    if (!selected.length) return "Upload at least one supporting file.";
    if (selected.length > options.max_files) {
      return `Upload no more than ${options.max_files} files.`;
    }
    const maxBytes = options.max_file_size_mb * 1024 * 1024;
    for (const file of selected) {
      const extension = file.name.includes(".")
        ? `.${file.name.split(".").pop()?.toLowerCase()}`
        : "";
      if (!acceptedExtensions.includes(extension)) {
        return `${file.name} has an unsupported file type.`;
      }
      if (file.size > maxBytes) {
        return `${file.name} is larger than ${options.max_file_size_mb} MB.`;
      }
    }
    return "";
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const fileError = validateFiles(files);
    if (fileError) {
      setError(fileError);
      setStep(2);
      return;
    }
    if (!canContinueAcademic || !requestKey) {
      setError("Complete the curriculum, subject, grade and topic fields.");
      setStep(1);
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData(event.currentTarget);
      const response = await fetch("/api/custom-video/requests", {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as {
        request_reference?: string;
        detail?: string;
      };
      if (!response.ok || !payload.request_reference) {
        throw new Error(payload.detail || "Request could not be created.");
      }
      window.location.assign(
        `/request-your-own-video/checkout?reference=${encodeURIComponent(payload.request_reference)}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We could not create your request. Please try again.",
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-8 rounded-[2rem] border border-[#dce4ef] bg-white p-6 shadow-[0_22px_70px_rgba(9,35,75,.08)] sm:p-8"
    >
      <input type="hidden" name="idempotency_key" value={requestKey} />
      <ol
        className="grid gap-3 md:grid-cols-5"
        aria-label="Custom video request steps"
      >
        {[
          ["1", "Curriculum"],
          ["2", "Files"],
          ["3", "Review"],
          ["4", "Payment"],
          ["5", "Invoice"],
        ].map(([number, label]) => {
          const active = Number(number) === step;
          const complete = Number(number) < step;
          return (
            <li
              key={number}
              className={`rounded-xl border px-4 py-3 text-sm ${
                active
                  ? "border-[#1f5bbd] bg-[#edf3ff] text-[#0b2a5b]"
                  : complete
                    ? "border-[#bfe3d8] bg-[#eefaf6] text-[#13715f]"
                    : "border-[#dce4ef] text-[#60708a]"
              }`}
              aria-current={active ? "step" : undefined}
            >
              <span className="font-bold">{number}.</span> {label}
            </li>
          );
        })}
      </ol>

      {error && (
        <div
          role="alert"
          className="mt-6 rounded-xl border border-[#efc3c3] bg-[#fff1f1] p-4 text-sm text-[#8a2525]"
        >
          {error}
        </div>
      )}

      <section className={step === 1 ? "mt-8" : "hidden"} aria-labelledby="video-step-1">
        <p className="eyebrow">Step 1</p>
        <h2 id="video-step-1" className="mt-2 text-3xl font-semibold tracking-[-.035em]">
          Tell us what video you need
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[#60708a]">
          Choose the curriculum and subject, then enter the exact topic. Amaris does
          not invent curriculum topics that are not modelled in the academy catalogue.
        </p>
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold">
            Curriculum
            <select
              name="curriculum"
              required
              value={curriculum}
              onChange={(event) => setCurriculum(event.target.value)}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
            >
              <option value="">Choose curriculum</option>
              {options.curricula.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold">
            Subject
            <select
              name="subject"
              required
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
            >
              <option value="">Choose subject</option>
              {options.subjects.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold">
            Grade
            <select
              name="grade"
              required
              value={grade}
              onChange={(event) => setGrade(event.target.value)}
              className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
            >
              <option value="">Choose grade</option>
              {options.grades.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold">
            Topic
            <input
              name="topic"
              required
              minLength={2}
              maxLength={220}
              list={options.modelled_topics.length ? "custom-video-topics" : undefined}
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="Enter the exact topic or question"
              className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
            />
            {options.modelled_topics.length > 0 && (
              <datalist id="custom-video-topics">
                {options.modelled_topics.map((item) => <option key={item} value={item} />)}
              </datalist>
            )}
            <span className="font-normal text-[#60708a]">{options.topic_note}</span>
          </label>
        </div>
        <button
          type="button"
          disabled={!canContinueAcademic}
          onClick={() => {
            setError("");
            setStep(2);
          }}
          className="mt-7 inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-45"
        >
          Continue to files <ArrowRight className="size-4" />
        </button>
      </section>

      <section className={step === 2 ? "mt-8" : "hidden"} aria-labelledby="video-step-2">
        <p className="eyebrow">Step 2</p>
        <h2 id="video-step-2" className="mt-2 text-3xl font-semibold tracking-[-.035em]">
          Upload supporting files
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[#60708a]">
          You can upload up to {options.max_files} files. Each file may be up to{" "}
          {options.max_file_size_mb} MB. Accepted formats include PDF, JPG, PNG, HEIC,
          Word, PowerPoint, Excel and plain text. The server validates every upload.
        </p>
        <label className="mt-6 flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[#b8c8dc] bg-[#f8fbff] p-6 text-center">
          <Upload className="size-8 text-[#1f5bbd]" />
          <span className="mt-3 font-semibold">Choose supporting files</span>
          <span className="mt-1 text-sm text-[#60708a]">Multiple files are supported</span>
          <input
            className="sr-only"
            type="file"
            name="files"
            multiple
            required
            accept={acceptedExtensions.join(",")}
            onChange={(event) => {
              const selected = Array.from(event.target.files ?? []);
              setFiles(selected);
              setError(validateFiles(selected));
            }}
          />
        </label>
        {files.length > 0 && (
          <ul className="mt-5 grid gap-2" aria-label="Selected supporting files">
            {files.map((file) => (
              <li
                key={`${file.name}-${file.size}`}
                className="flex items-center gap-3 rounded-xl border border-[#dce4ef] px-4 py-3 text-sm"
              >
                <FileText className="size-4 shrink-0 text-[#1f5bbd]" />
                <span className="min-w-0 flex-1 truncate">{file.name}</span>
                <span className="text-[#60708a]">
                  {(file.size / (1024 * 1024)).toFixed(1)} MB
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-7 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setStep(1)}
            className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#c9d5e5] px-6 py-3 font-bold text-[#0b2a5b]"
          >
            <ArrowLeft className="size-4" /> Back
          </button>
          <button
            type="button"
            disabled={Boolean(validateFiles(files))}
            onClick={() => {
              const fileError = validateFiles(files);
              setError(fileError);
              if (!fileError) setStep(3);
            }}
            className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            Review request <ArrowRight className="size-4" />
          </button>
        </div>
      </section>

      <section className={step === 3 ? "mt-8" : "hidden"} aria-labelledby="video-step-3">
        <p className="eyebrow">Step 3</p>
        <h2 id="video-step-3" className="mt-2 text-3xl font-semibold tracking-[-.035em]">
          Review before payment
        </h2>
        <dl className="mt-6 grid gap-4 rounded-2xl bg-[#f7f9fc] p-5 text-sm md:grid-cols-2">
          <div><dt className="font-semibold text-[#263852]">Curriculum</dt><dd className="mt-1 text-[#60708a]">{options.curricula.find((item) => item.value === curriculum)?.label}</dd></div>
          <div><dt className="font-semibold text-[#263852]">Subject</dt><dd className="mt-1 text-[#60708a]">{options.subjects.find((item) => item.value === subject)?.label}</dd></div>
          <div><dt className="font-semibold text-[#263852]">Grade</dt><dd className="mt-1 text-[#60708a]">{options.grades.find((item) => item.value === grade)?.label}</dd></div>
          <div><dt className="font-semibold text-[#263852]">Files</dt><dd className="mt-1 text-[#60708a]">{files.length}</dd></div>
          <div className="md:col-span-2"><dt className="font-semibold text-[#263852]">Topic</dt><dd className="mt-1 text-[#60708a]">{topic}</dd></div>
          <div className="md:col-span-2"><dt className="font-semibold text-[#263852]">Configured price</dt><dd className="mt-1 text-xl font-bold text-[#0b2a5b]">{amount}</dd></div>
        </dl>
        <div className="mt-5 flex items-start gap-3 rounded-xl border border-[#cfe0f5] bg-[#f5f9ff] p-4 text-sm leading-6 text-[#47617e]">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#1f5bbd]" />
          Payment is created server-side using the academy-configured fee. Your invoice
          is generated only after PayFast verifies the payment.
        </div>
        <div className="mt-7 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setStep(2)}
            className="inline-flex min-h-12 items-center gap-2 rounded-full border border-[#c9d5e5] px-6 py-3 font-bold text-[#0b2a5b]"
          >
            <ArrowLeft className="size-4" /> Back
          </button>
          <button
            type="submit"
            disabled={submitting || !requestKey}
            className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white disabled:cursor-wait disabled:opacity-55"
          >
            {submitting ? "Saving request…" : "Continue to secure payment"}
            {!submitting && <ArrowRight className="size-4" />}
          </button>
        </div>
      </section>
    </form>
  );
}
