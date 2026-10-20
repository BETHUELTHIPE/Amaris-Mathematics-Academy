"use client";

import { useReportWebVitals } from "next/web-vitals";

// This is a 25% anonymous sample, not a login/activity tracker. Never transmit
// user IDs, URLs, tokens, interaction targets, event entries or query strings.
const DASHBOARDS: Record<string, string> = {
  "/dashboard": "student_overview",
  "/dashboard/orders": "student_orders",
  "/dashboard/notifications": "student_notifications",
  "/tutor/dashboard": "tutor_dashboard",
};
const SAMPLE_RATE = 0.25;
let included: boolean | undefined;

type Vital = Parameters<typeof useReportWebVitals>[0] extends (metric: infer M) => void ? M : never;

function reportDashboardVital(metric: Vital) {
  if (typeof window === "undefined") return;
  if (included === undefined) included = Math.random() < SAMPLE_RATE;
  if (!included) return;

  const page = DASHBOARDS[window.location.pathname.replace(/\/$/, "")];
  if (!page || !["LCP", "INP", "CLS"].includes(metric.name)) return;
  if (!Number.isFinite(metric.value) || metric.value < 0) return;

  // Avoid cookies and referer on this explicitly anonymous measurement.
  const body = JSON.stringify({
    page,
    device: window.innerWidth < 768 ? "mobile" : "desktop",
    metric: metric.name,
    value: Number(metric.value.toFixed(metric.name === "CLS" ? 4 : 0)),
  });
  void fetch("/api/monitoring/web-vitals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
    credentials: "omit",
    referrerPolicy: "no-referrer",
    keepalive: true,
  }).catch(() => {
    // Telemetry is never allowed to interrupt students or tutor bookings.
  });
}

export function DashboardRealUserVitals() {
  useReportWebVitals(reportDashboardVital);
  return null;
}
