/**
 * Tutor applicants choose concrete teaching windows in South African Standard Time
 * (SAST; fixed UTC+02:00). No browser-local timezone conversions are involved.
 * The backend currently stores availability as text: derive that text on the
 * server from validated repeated date/time and duration inputs.
 */
export const MAX_TUTOR_AVAILABILITY_SLOTS = 12;
const SAST_OFFSET_MS = 2 * 60 * 60 * 1000;
const MAX_AHEAD_MS = 366 * 24 * 60 * 60 * 1000;
const FIELD_START = "availability_start";
const FIELD_HOURS = "availability_duration_hours";

export type TutorAvailabilitySlot = { start: string; durationHours: number };
export type AvailabilityResult =
  | { ok: true; slots: TutorAvailabilitySlot[]; summary: string }
  | { ok: false; error: string };

export function validateTutorAvailability(values: FormData, now = Date.now()): AvailabilityResult {
  const dates = values.getAll(FIELD_START);
  const hours = values.getAll(FIELD_HOURS);
  if (!dates.length || dates.length !== hours.length || dates.length > MAX_TUTOR_AVAILABILITY_SLOTS) {
    return { ok: false, error: "Choose between 1 and 12 available teaching dates and times." };
  }
  const times: { startMs: number; endMs: number; dateText: string; durationHours: number }[] = [];
  for (let i = 0; i < dates.length; i++) {
    const value = dates[i], length = hours[i];
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
      return { ok: false, error: "Select a valid date and start time for every availability slot." };
    }
    if (typeof length !== "string" || !/^(?:[1-9]|1\d|2[0-4])$/.test(length)) {
      return { ok: false, error: "Choose a whole-number duration between 1 and 24 hours for each slot." };
    }
    const durationHours = Number(length);
    const [year, month, day, hour, minute] = value.split(/[-T:]/).map(Number);
    const startMs = Date.UTC(year, month - 1, day, hour, minute) - SAST_OFFSET_MS;
    // Reject rolled-over dates (e.g. 31 February) and non-half-hour starts.
    const roundTrip = new Date(startMs + SAST_OFFSET_MS).toISOString().slice(0, 16);
    if (roundTrip !== value || minute % 30 !== 0) {
      return { ok: false, error: "Choose a real calendar date and start on the hour or half-hour." };
    }
    if (startMs <= now || startMs > now + MAX_AHEAD_MS) {
      return { ok: false, error: "Choose a future teaching date within the next 12 months (South African time)." };
    }
    times.push({ startMs, endMs: startMs + durationHours * 3600000, dateText: value, durationHours });
  }
  times.sort((a, b) => a.startMs - b.startMs);
  for (let i = 1; i < times.length; i++) {
    if (times[i].startMs < times[i - 1].endMs) {
      return { ok: false, error: "Your available teaching times overlap. Adjust or remove one of the slots." };
    }
  }
  const summary = [
    "Selected teaching availability — South African Standard Time (UTC+02:00):",
    ...times.map(({ startMs, endMs, durationHours }) => {
      const localStart = new Date(startMs + SAST_OFFSET_MS).toISOString().slice(0, 16).replace("T", " ");
      const localEnd = new Date(endMs + SAST_OFFSET_MS).toISOString().slice(0, 16).replace("T", " ");
      return `${localStart} to ${localEnd} (${durationHours} ${durationHours === 1 ? "hour" : "hours"})`;
    }),
  ].join("\n");
  if (summary.length > 2000) {
    return { ok: false, error: "Too many teaching hours or dates have been selected." };
  }
  return {
    ok: true,
    slots: times.map(t => ({ start: t.dateText, durationHours: t.durationHours })),
    summary,
  };
}
