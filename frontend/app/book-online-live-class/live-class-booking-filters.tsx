"use client";

import { CurriculumFields } from "@/components/site/curriculum-fields";

type Props = {
  initialProgramme: string;
  initialSubject: string;
  initialLevel: string;
  initialTopic: string;
  initialTutorId?: string;
  initialTimePreference?: string;
  offeredLevels: string[];
  tutors?: { id: number; name: string }[];
};

export function LiveClassBookingFilters(props: Props) {
  return (
    <form method="get" className="mt-8 grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:grid-cols-2">
      <CurriculumFields {...props} />
      <div>
        <label htmlFor="preferred-tutor" className="mb-2 block text-sm font-semibold text-[#263852]">
          Choose your tutor
        </label>
        <select
          id="preferred-tutor"
          name="tutor"
          key={props.initialTutorId}
          defaultValue={props.initialTutorId ?? ""}
          className="min-h-12 w-full rounded-xl border border-[#b7c5d8] bg-white px-4 py-3 text-[#263852]"
        >
          <option value="">Any available tutor — show me the earliest</option>
          {(props.tutors ?? []).map((tutor) => (
            <option key={tutor.id} value={tutor.id}>{tutor.name}</option>
          ))}
        </select>
        <p className="mt-2 text-xs leading-5 text-[#60708a]">Only tutors with published, available times appear here.</p>
      </div>
      <div>
        <label htmlFor="preferred-time" className="mb-2 block text-sm font-semibold text-[#263852]">
          Your preferred time (South African time)
        </label>
        <select
          id="preferred-time"
          name="time"
          defaultValue={props.initialTimePreference ?? "any"}
          className="min-h-12 w-full rounded-xl border border-[#b7c5d8] bg-white px-4 py-3 text-[#263852]"
        >
          <option value="any">Any time — 24/7</option>
          <option value="morning">Morning · 05:00–11:59</option>
          <option value="afternoon">Afternoon · 12:00–16:59</option>
          <option value="evening">Evening · 17:00–21:59</option>
          <option value="overnight">Overnight · 22:00–04:59</option>
        </select>
        <p className="mt-2 text-xs leading-5 text-[#60708a]">Early-morning and overnight classes are welcome when a tutor has opened a slot.</p>
      </div>
      <p className="text-xs leading-6 text-[#60708a] lg:col-span-2">
        Choose your grade, chapter and preferred tutor. You can book at any hour, subject to a tutor's published availability. Zoom details are kept private until payment is verified.
      </p>
      <div className="flex flex-wrap gap-3 lg:col-span-2">
        <button type="submit" className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white">
          Find my tutor and time
        </button>
        <button type="submit" formNoValidate name="update_choices" value="1" className="inline-flex min-h-12 items-center justify-center rounded-full border border-[#b7c5d8] px-5 py-3 font-semibold text-[#0b2a5b]">
          Update grade and topic choices
        </button>
      </div>
    </form>
  );
}
