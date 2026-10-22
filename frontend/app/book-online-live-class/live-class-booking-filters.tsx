"use client";

import { CurriculumFields } from "@/components/site/curriculum-fields";

type Props = {
  initialProgramme: string;
  initialSubject: string;
  initialLevel: string;
  initialTopic: string;
  offeredLevels: string[];
};

export function LiveClassBookingFilters(props: Props) {
  return (
    <form method="get" className="mt-8 grid gap-5 rounded-3xl border border-[#dce4ef] bg-white p-6 sm:p-8 lg:grid-cols-2">
      <CurriculumFields {...props} />
      <p className="text-xs leading-6 text-[#60708a] lg:col-span-2">Choose your grade and chapter even when no tutor times are listed. Available sessions appear after you search.</p>
      <div className="flex flex-wrap gap-3 lg:col-span-2">
        <button type="submit" className="inline-flex min-h-12 items-center justify-center rounded-full bg-[#0b2a5b] px-7 py-3 font-bold text-white">Show available tutor times</button>
        <button type="submit" formNoValidate name="update_choices" value="1" className="inline-flex min-h-12 items-center justify-center rounded-full border border-[#b7c5d8] px-5 py-3 font-semibold text-[#0b2a5b]">Update grade and topic choices</button>
      </div>
    </form>
  );
}
