// Anonymous, coarse browser-performance telemetry. NEVER record user identity,
// full URLs, cookies, headers, emails, raw browser events, or any account data.
// No database migration or paid telemetry service is required.
const ROUTES = new Set([
  "home", "courses", "announcements", "contact", "matric_upgrades", "booking",
  "student_overview", "student_orders", "student_notifications", "tutor_dashboard",
]);
const METRICS = new Set(["LCP", "INP", "CLS"]);
const DEVICES = new Set(["mobile", "desktop"]);
let minuteStart = 0;
let acceptedInMinute = 0;

const response = (status: number) => new Response(null, {
  status,
  headers: {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  },
});

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin || origin !== new URL(request.url).origin) return response(403);
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin") return response(403);
  if (!request.headers.get("content-type")?.startsWith("application/json")) return response(415);
  const length = Number(request.headers.get("content-length") || "0");
  if (!Number.isFinite(length) || length > 256 || length < 0) return response(413);

  let raw: string;
  try {
    raw = await request.text();
  } catch {
    return response(400);
  }
  if (raw.length > 256) return response(413);
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return response(400);
  }
  if (data === null || typeof data !== "object" || Array.isArray(data)) return response(400);
  const input = data as Record<string, unknown>;
  if (Object.keys(input).sort().join(",") !== "device,metric,page,value") return response(400);
  const { device, metric, page, value } = input;
  if (typeof device !== "string" || !DEVICES.has(device)) return response(400);
  if (typeof metric !== "string" || !METRICS.has(metric)) return response(400);
  if (typeof page !== "string" || !ROUTES.has(page)) return response(400);
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return response(400);
  if (value > (metric === "CLS" ? 5 : metric === "LCP" ? 120000 : 60000)) return response(400);

  // Limit unauthenticated log volume per process. This cap is deliberately
  // account-agnostic; we do not inspect IP addresses or session cookies.
  const now = Date.now();
  if (now - minuteStart > 60_000) {
    minuteStart = now;
    acceptedInMinute = 0;
  }
  if (++acceptedInMinute > 300) return response(429);

  // No identifier or exact URL is logged. Render logs are temporary; reporting
  // p75 requires collecting enough real user samples for each route and metric.
  // The release SHA is injected by Render SERVER-SIDE and is never accepted
  // from the browser. This permits accurate per-release p75 comparisons.
  const release = (process.env.RENDER_GIT_COMMIT || "").slice(0, 12);
  console.info("amaris_dashboard_vital", JSON.stringify({ page, device, metric, value, release }));
  return response(204);
}
