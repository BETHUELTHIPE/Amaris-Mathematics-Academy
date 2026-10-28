"use client";

import { useState } from "react";
import { MAX_TUTOR_AVAILABILITY_SLOTS } from "@/lib/tutor-availability";

const control = "min-h-12 w-full min-w-0 rounded-xl border border-[#cbd6e5] bg-white px-3 py-2 text-base font-normal text-[#263852] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd]";

/** Available days and lesson lengths are proposed dates, not booked/published slots. */
export function TutorAvailabilityPicker() {
  const [ids, setIds] = useState([0]);
  const [nextId, setNextId] = useState(1);

  return (
    <section id="availability" aria-labelledby="availability-heading" className="rounded-2xl border border-[#cbd6e5] bg-[#f5f7fb] p-5 sm:p-6">
      <h3 id="availability-heading" className="text-lg font-semibold text-[#07152d]">
        Choose your available teaching dates and times
      </h3>
      <p id="availability-help" className="mt-2 text-sm leading-6 text-[#52617a]">
        Select at least one future date and start time. All times are South African Standard Time
        (SAST, UTC+02:00), including evenings and weekends. Choose 1–24 whole teaching hours per
        slot. Add up to 12 non-overlapping slots for the next year.
      </p>
      <p className="mt-2 text-xs leading-5 text-[#52617a]">
        Your choices tell Amaris when you would like to teach. They are reviewed with your
        application and are not published for student booking until tutor approval.
      </p>
      <div className="mt-5 grid gap-4">
        {ids.map((id, index) => (
          <div key={id} className="rounded-xl border border-[#dce4ef] bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-sm font-bold text-[#263852]">Available session {index + 1}</h4>
              {ids.length > 1 && (
                <button type="button" className="min-h-11 rounded-full border border-[#cbd6e5] px-4 text-sm font-semibold text-[#1f5bbd] hover:bg-[#eef4fc]" aria-label={`Remove available session ${index + 1}`} onClick={() => setIds(current => current.filter(item => item !== id))}>
                  Remove slot
                </button>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <label className="grid gap-2 text-sm font-semibold text-[#263852]">
                Date and start time (SAST)
                <input name="availability_start" type="datetime-local" step={1800} required aria-describedby="availability-help" className={control} />
              </label>
              <label className="grid gap-2 text-sm font-semibold text-[#263852]">
                Available teaching hours
                <select name="availability_duration_hours" defaultValue="1" required className={control}>
                  {Array.from({ length: 24 }, (_, i) => i + 1).map(hours => (
                    <option key={hours} value={hours}>{hours} {hours === 1 ? "hour" : "hours"}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        ))}
      </div>
      {ids.length < MAX_TUTOR_AVAILABILITY_SLOTS && (
        <button type="button" className="mt-5 min-h-12 rounded-full border border-[#1f5bbd] bg-white px-5 font-bold text-[#1f5bbd] hover:bg-[#eaf1fb]" onClick={() => { setIds(current => [...current, nextId]); setNextId(id => id + 1); }}>
          + Add another date and time
        </button>
      )}
      <p className="mt-3 text-sm text-[#52617a]" role="status">
        {ids.length} of {MAX_TUTOR_AVAILABILITY_SLOTS} available sessions selected.
      </p>
    </section>
  );
}
