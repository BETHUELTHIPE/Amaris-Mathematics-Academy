/** Coarse privacy-safe dimensions; never transmit URLs, query params or IDs. */
export type VitalName = "LCP" | "INP" | "CLS";
export type DeviceClass = "mobile" | "tablet" | "desktop";
export type PageGroup =
  | "home" | "courses" | "course-detail" | "announcements" | "contact"
  | "booking" | "student" | "tutor" | "auth" | "other";

export type VitalPayload = {
  name: VitalName;
  value: number;
  id: string;
  page: PageGroup;
  device: DeviceClass;
};

export function groupPage(pathname: string): PageGroup {
  // Examine only the pathname: discard search, fragments and any identifiers.
  if (pathname === "/") return "home";
  if (pathname === "/courses") return "courses";
  if (pathname.startsWith("/courses/")) return "course-detail";
  if (pathname === "/announcements") return "announcements";
  if (pathname === "/contact") return "contact";
  if (/^\/(book|booking|live-class)(\/|$|-)/.test(pathname)) return "booking";
  if (/^\/(student|dashboard|my-courses|orders|payment)(\/|$|-)/.test(pathname)) return "student";
  if (/^\/tutor(\/|$|-)/.test(pathname)) return "tutor";
  if (/^\/(login|register|signup|sign-in|reset-password|forgot-password)(\/|$)/.test(pathname)) return "auth";
  return "other";
}

export function groupDevice(width: number): DeviceClass {
  return width <= 600 ? "mobile" : width <= 1024 ? "tablet" : "desktop";
}

export function validVital(payload: unknown): payload is VitalPayload {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  const fields = payload as Record<string, unknown>;
  const allowed = ["name", "value", "id", "page", "device"];
  if (Object.keys(fields).length !== allowed.length || Object.keys(fields).some((key) => !allowed.includes(key))) return false;
  const upper = fields.name === "CLS" ? 10 : 60000;
  return (fields.name === "LCP" || fields.name === "INP" || fields.name === "CLS") &&
    typeof fields.value === "number" && Number.isFinite(fields.value) && fields.value >= 0 &&
    fields.value <= upper &&
    typeof fields.id === "string" && /^[A-Za-z0-9_.:-]{6,128}$/.test(fields.id) &&
    ["home", "courses", "course-detail", "announcements", "contact", "booking", "student", "tutor", "auth", "other"].includes(fields.page as string) &&
    ["mobile", "tablet", "desktop"].includes(fields.device as string);
}
