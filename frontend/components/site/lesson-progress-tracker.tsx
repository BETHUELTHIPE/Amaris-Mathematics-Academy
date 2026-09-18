"use client";

import { useRef } from "react";
import { saveProgressAction } from "@/app/learn/actions";

export function LessonProgressTracker({
  courseSlug,
  lessonSlug,
  videoUrl,
  initialPositionSeconds,
}: {
  courseSlug: string;
  lessonSlug: string;
  videoUrl: string | null;
  initialPositionSeconds: number;
}) {
  const positionRef = useRef<HTMLInputElement>(null);

  return <div className="mt-8">
    {videoUrl ? <video
      className="w-full rounded-2xl bg-black"
      controls
      preload="metadata"
      src={videoUrl}
      onLoadedMetadata={(event) => {
        const video = event.currentTarget;
        if (initialPositionSeconds > 0 && initialPositionSeconds < video.duration) video.currentTime = initialPositionSeconds;
      }}
      onTimeUpdate={(event) => {
        if (positionRef.current) positionRef.current.value = String(Math.floor(event.currentTarget.currentTime));
      }}
    /> : null}
    <form action={saveProgressAction} className="mt-5 flex flex-col gap-3 sm:flex-row">
      <input type="hidden" name="courseSlug" value={courseSlug} />
      <input type="hidden" name="lessonSlug" value={lessonSlug} />
      <input ref={positionRef} type="hidden" name="positionSeconds" defaultValue={initialPositionSeconds} />
      <button type="submit" className="min-h-11 rounded-full border border-[#b9c9df] px-5 py-2.5 font-semibold text-[#0b2a5b]">Save my place</button>
      <button type="submit" name="completed" value="true" className="min-h-11 rounded-full bg-[#0b2a5b] px-5 py-2.5 font-bold text-white">Mark lesson complete</button>
    </form>
  </div>;
}
