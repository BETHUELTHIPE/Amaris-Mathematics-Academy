import "server-only";
import { normalizeCmsApiBaseUrl } from "@/lib/cms-api-url";

export function donationApiBase(requestUrl: string): string {
  const configured = (process.env.CMS_API_URL || "").trim();
  if (configured) {
    try {
      return normalizeCmsApiBaseUrl(configured);
    } catch {
      return "";
    }
  }
  const host = new URL(requestUrl).hostname;
  if (host === "amaris-mathematics-academy-live-students.onrender.com") {
    return "https://amaris-production-web.onrender.com/api/v1";
  }
  // Do not accidentally route staging or preview donations into production.
  return "";
}

export function sameOrigin(request: Request): boolean {
  const actualOrigin = request.headers.get("origin");
  if (!actualOrigin) return true;
  const current = new URL(request.url);
  const forwarded = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  if (forwarded === "https" || forwarded === "http") current.protocol = forwarded + ":";
  return actualOrigin === current.origin;
}

export function isValidDonationReference(reference: string): boolean {
  return /^DON-[A-Za-z0-9_-]{12,64}$/.test(reference);
}
