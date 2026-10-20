"use client";

import { useReportWebVitals } from "next/web-vitals";

// One anonymous 25% browser sample for public pages and selected dashboards.
// Never transmit identities, URLs, tokens, interaction targets or query strings.
const DASHBOARDS: Record<string, string> = {
  "/": "home",
  "/courses": "courses",
  "/announcements": "announcements",
  "/contact": "contact",
  "/matric-upgrades": "matric_upgrades",
  "/book-online-live-class": "booking",
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
  // Honor explicit browser privacy signals as a further safeguard.
  if (navigator.doNotTrack === "1" || (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true) return;
  if (included === undefined) included = Math.random() < SAMPLE_RATE;
  if (!included) return;

  const pathname = window.location.pathname;
  // Exact allowlist only. Never send personalised course slugs, checkout,
  // registration, invoice, profile, account or payment route information.
  const page = DASHBOARDS[pathname === "/" ? "/" : pathname.replace(/\/$/, "")];
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
