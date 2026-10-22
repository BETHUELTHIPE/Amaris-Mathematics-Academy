"use client";

import { useState } from "react";
import {
  getGradeLevels,
  gradeLevelsByProgramme,
  programmes,
  subjects,
} from "@/lib/booking-grade-levels.mjs";

type Props = {
  initialProgramme: string;
  initialSubject: string;
  initialLevel: string;
  initialTopic: string;
  offeredLevels: string[];
};

export function LiveClassBookingFilters({
  initialProgramme,
  initialSubject,
  initialLevel,
  initialTopic,
  offeredLevels,
}: Props) {
  const [programme, setProgramme] = useState(initialProgramme);
  const [subject, setSubject] = useState(initialSubject);
  const [level, setLevel] = useState(initialLevel);

  // Extra tutor-configured levels are relevant only to the initial programme
  // and subject used to fetch this page. Never carry them into a new selection.
  const matchingOfferedLevels =
    programme === initialProgramme && subject === initialSubject
      ? offeredLevels
      : [];
  const levels = getGradeLevels(programme, matchingOfferedLevels);

  return (
    <form
      method="get"
      className="mt-8 grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:grid-cols-2"
    >
      <label className="grid gap-2 text-sm font-semibold">
        Programme
        <select
          name="programme"
          required
          value={programme}
          onChange={(event) => {
            setProgramme(event.target.value);
            setLevel("");
          }}
          className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
        >
          <option value="">Choose programme</option>
          {programmes.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>

      <label className="grid gap-2 text-sm font-semibold">
        Subject
        <select
          name="subject"
          required
          value={subject}
          onChange={(event) => {
            setSubject(event.target.value);
            setLevel("");
          }}
          className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
        >
          <option value="">Choose subject</option>
          {subjects.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>

      <label className="grid gap-2 text-sm font-semibold">
        Grade / level
        <select
          name="level"
          required
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          aria-describedby="live-class-level-help"
          className="min-h-12 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal"
        >
          <option value="">Choose grade / level</option>
          {programme
            ? levels.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))
            : Object.entries(gradeLevelsByProgramme).map(([key, items]) => (
                <optgroup
                  key={key}
                  label={programmes.find(([value]) => value === key)?.[1] ?? key}
                >
                  {items.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </optgroup>
              ))}
        </select>
        <span id="live-class-level-help" className="text-xs font-normal leading-5 text-[#60708a]">
          Choose your grade or academic level even when no tutor times are listed.
          Available sessions will appear after you search.
        </span>
      </label>

      <label className="grid gap-2 text-sm font-semibold">
        Topic
        <input
          name="topic"
          required
          minLength={2}
          maxLength={180}
          defaultValue={initialTopic}
          placeholder="e.g. Grade 12 Calculus — differentiation"
          className="min-h-12 rounded-xl border border-[#c9d5e5] px-4 font-normal"
        />
      </label>

      <div className="lg:col-span-2">
        <button
          type="submit"
          className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white"
        >
          Show available tutor times
        </button>
      </div>
    </form>
  );
}
