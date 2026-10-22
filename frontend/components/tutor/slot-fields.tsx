import { CurriculumFields } from "@/components/site/curriculum-fields";
import type { TutorSlot } from "@/lib/tutor-api";

const formDateFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Africa/Johannesburg", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function localDateTime(value: string): string {
  const parts = formDateFormatter.formatToParts(new Date(value));
  const part = (name: string) => parts.find((item) => item.type === name)?.value || "00";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function TutorSlotFields({ slot }: { slot?: TutorSlot }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <CurriculumFields initialProgramme={slot?.programme ?? "caps"} initialSubject={slot?.subject ?? "mathematics"} initialLevel={slot?.level ?? ""} offeredLevels={slot ? [slot.level] : []} includeTopic={false} />
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Session start (South Africa time)
        <input name="starts_at" type="datetime-local" required defaultValue={slot ? localDateTime(slot.starts_at) : undefined} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Number of hours
        <input name="duration_hours" type="number" required min={1} max={24} step={1} defaultValue={slot?.duration_hours ?? 1} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
        <span className="text-xs font-normal text-[#60708a]">R250 per whole hour; the end time is calculated automatically.</span>
      </label>
      <label className="grid gap-2 text-sm font-semibold text-[#263852]">
        Zoom meeting link
        <input name="zoom_join_url" type="url" required placeholder="https://..." defaultValue={slot?.zoom_join_url ?? ""} className="min-h-12 rounded-xl border border-[#dce4ef] px-3 font-normal" />
        <span className="text-xs font-normal text-[#60708a]">This link is kept private until a student&apos;s payment is confirmed.</span>
      </label>
      <label className="flex items-center gap-3 text-sm font-semibold text-[#263852] sm:col-span-2">
        <input type="checkbox" name="is_active" defaultChecked={slot?.is_active ?? true} className="size-5 accent-[#1f5bbd]" />
        Publish this slot for student booking
      </label>
    </div>
  );
}

