// Anonymous, coarse browser-performance telemetry. NEVER record user identity,
// full URLs, cookies, headers, emails, raw browser events, or any account data.
// No database migration or paid telemetry service is required.
const ROUTES = new Set([
  "student_overview", "student_orders", "student_notifications", "tutor_dashboard",
]);
const METRICS = new Set(["LCP", "INP", "CLS"]);

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
  if (Object.keys(input).sort().join(",") !== "metric,page,value") return response(400);
  const { metric, page, value } = input;
  if (typeof metric !== "string" || !METRICS.has(metric)) return response(400);
  if (typeof page !== "string" || !ROUTES.has(page)) return response(400);
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return response(400);
  if (value > (metric === "CLS" ? 5 : metric === "LCP" ? 120000 : 60000)) return response(400);

  // No identifier or exact URL is logged. Render logs are temporary; reporting
  // p75 requires collecting enough real user samples for each route and metric.
  console.info("amaris_dashboard_vital", JSON.stringify({ page, metric, value }));
  return response(204);
}
