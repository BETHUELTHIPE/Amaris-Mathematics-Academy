import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const APPROVED = new Set(["name", "value", "route", "device", "network"]);
const NAMES = new Set(["LCP", "INP", "CLS"]);
const ROUTES = new Set(["home", "courses", "contact", "announcements", "matric", "booking", "student", "tutor", "other-public"]);
const DEVICES = new Set(["mobile", "tablet", "desktop"]);
const NETWORKS = new Set(["slow-2g", "2g", "3g", "4g", "unknown"]);
let currentMinute = 0;
let acceptedThisMinute = 0;
const MAX_REPORTS_PER_MINUTE = 300; // process-local, never indexed by IP or account


/** Same-origin public beacon, forwarded server-to-server with a private secret. */
export async function POST(request: NextRequest) {
  const cache = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" };
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin) {
    return new NextResponse(null, { status: 403, headers: cache });
  }
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") {
    return new NextResponse(null, { status: 403, headers: cache });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return new NextResponse(null, { status: 415, headers: cache });
  }
  if (process.env.RUM_FORWARD_ENABLED !== "true") {
    return new NextResponse(null, { status: 503, headers: cache });
  }
  const key = process.env.RUM_INGEST_TOKEN;
  const release = (process.env.RENDER_GIT_COMMIT || "").slice(0, 12);
  const base = process.env.CMS_API_URL?.replace(/\/$/, "");
  if (!key || key.length < 32 || !/^[a-f0-9]{12}$/.test(release) || !base || !base.startsWith("https://")) {
    return new NextResponse(null, { status: 503, headers: cache });
  }

  try {
    if (Number(request.headers.get("content-length") || 0) > 1800) {
      return new NextResponse(null, { status: 413, headers: cache });
    }
    const body = await request.text();
    if (body.length > 1800) return new NextResponse(null, { status: 413, headers: cache });
    const data: unknown = JSON.parse(body);
    if (!data || typeof data !== "object" || Array.isArray(data) ||
        Object.keys(data).join(",") !== "records") {
      return new NextResponse(null, { status: 400, headers: cache });
    }
    const values = (data as { records: unknown }).records;
    if (!Array.isArray(values) || values.length < 1 || values.length > 3) {
      return new NextResponse(null, { status: 400, headers: cache });
    }
    const records = [];
    for (const item of values) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return new NextResponse(null, { status: 400, headers: cache });
      }
      const v = item as Record<string, unknown>;
      if (Object.keys(v).some((field) => !APPROVED.has(field)) || Object.keys(v).length !== 5 ||
          !NAMES.has(String(v.name)) || !ROUTES.has(String(v.route)) ||
          !DEVICES.has(String(v.device)) || !NETWORKS.has(String(v.network)) ||
          typeof v.value !== "number" || !Number.isFinite(v.value) || v.value < 0 ||
          v.value > (v.name === "CLS" ? 10 : v.name === "LCP" ? 120000 : 60000)) {
        return new NextResponse(null, { status: 400, headers: cache });
      }
      // Explicitly rebuild the payload; never relay unknown/private fields.
      records.push({ name: v.name, value: v.value, route: v.route, device: v.device, network: v.network });
    }
    // Bound public anonymous forwarding so a surge cannot overrun the shared
    // private histogram database. Never store an IP, cookie or visitor ID.
    const minute = Math.floor(Date.now() / 60000);
    if (minute !== currentMinute) {
      currentMinute = minute;
      acceptedThisMinute = 0;
    }
    if (++acceptedThisMinute > MAX_REPORTS_PER_MINUTE) {
      return new NextResponse(null, { status: 429, headers: cache });
    }
    const response = await fetch(`${base}/rum/`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Amaris-Rum-Token": key,
        "X-Amaris-Rum-Release": release,
      },
      body: JSON.stringify({ records }),
      signal: AbortSignal.timeout(3000),
    });
    return new NextResponse(null, { status: response.status === 204 ? 204 : 503, headers: cache });
  } catch {
    // Fail closed without logging payloads, IP addresses or browser identifiers.
    return new NextResponse(null, { status: 503, headers: cache });
  }
}
