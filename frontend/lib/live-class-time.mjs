/** @param {string} startsAt @param {string} preference */
export function inPreferredTime(startsAt, preference) {
  const date = new Date(startsAt);
  if (!Number.isFinite(date.getTime())) return false;
  if (preference === "any") return true;
  const hour = Number(new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit", hourCycle: "h23", timeZone: "Africa/Johannesburg",
  }).format(date));
  if (preference === "morning") return hour >= 5 && hour < 12;
  if (preference === "afternoon") return hour >= 12 && hour < 17;
  if (preference === "evening") return hour >= 17 && hour < 22;
  if (preference === "overnight") return hour >= 22 || hour < 5;
  return true;
}
