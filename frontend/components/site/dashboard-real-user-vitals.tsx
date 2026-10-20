"use client";

import { useEffect } from "react";
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

/* Real browser vitals, sampled independently at 20% on non-sensitive public
   pages and represented ONLY by a fixed coarse route, device, network, metric
   and numeric value. Never send an exact path, query, ID, referrer, cookie or
   event target. We reuse Next's existing Core Web Vitals observer: no extra
   JavaScript library or user session tracking is required. */
type RumRecord = {
  name: "LCP" | "INP" | "CLS";
  route: "home" | "courses" | "contact" | "announcements" | "matric" | "booking" | "student";
  device: "mobile" | "tablet" | "desktop";
  network: "slow-2g" | "2g" | "3g" | "4g" | "unknown";
  value: number;
};
let publicIncluded: boolean | undefined;
const pendingPublic = new Map<string, RumRecord>();
const PUBLIC_RATE = 0.20;

function publicRoute(path: string): RumRecord["route"] | null {
  if (/\/(payment|payments|checkout|orders|invoice|invoices|profile|security|login|register|auth|password|reset|account)(\/|$)/i.test(path)) return null;
  if (path === "/") return "home";
  if (path === "/courses" || path.startsWith("/courses/")) return "courses";
  if (path === "/contact") return "contact";
  if (path === "/announcements" || path.startsWith("/announcements/")) return "announcements";
  if (path === "/matric-upgrades" || path.startsWith("/matric-upgrades/")) return "matric";
  if (path === "/book-online-live-class") return "booking";
  if (path === "/dashboard" || path === "/tutor/dashboard") return "student";
  return null;
}

function recordPublicVital(metric: Vital) {
  if (process.env.NEXT_PUBLIC_ENABLE_WEB_VITALS !== "true") return;
  if (typeof window === "undefined" || !["LCP", "INP", "CLS"].includes(metric.name)) return;
  if (publicIncluded === undefined) publicIncluded = Math.random() < PUBLIC_RATE;
  if (!publicIncluded) return;
  const route = publicRoute(window.location.pathname.replace(/\/$/, "") || "/");
  if (!route || !Number.isFinite(metric.value) || metric.value < 0) return;
  const nav = navigator as Navigator & { connection?: { effectiveType?: string } };
  const rawNetwork = nav.connection?.effectiveType;
  const network: RumRecord["network"] = rawNetwork === "slow-2g" || rawNetwork === "2g" ||
    rawNetwork === "3g" || rawNetwork === "4g" ? rawNetwork : "unknown";
  const width = window.innerWidth;
  const device: RumRecord["device"] = width <= 600 ? "mobile" : width <= 1024 ? "tablet" : "desktop";
  const name = metric.name as RumRecord["name"];
  // Coalesce updates to the same metric during a navigation. No metric ID is
  // transmitted or retained: only the final latest value for each coarse path.
  pendingPublic.set(route + ":" + name, {
    name, route, device, network,
    value: Number(metric.value.toFixed(name === "CLS" ? 4 : 0)),
  });
}

function flushPublicVitals() {
  if (!pendingPublic.size) return;
  const records = [...pendingPublic.values()];
  pendingPublic.clear();
  for (let i = 0; i < records.length; i += 3) {
    try {
      void fetch("/api/field-vitals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ records: records.slice(i, i + 3) }),
        credentials: "omit",
        referrerPolicy: "no-referrer",
        cache: "no-store",
        keepalive: true,
      }).catch(() => undefined);
    } catch {
      // Reporting must never interfere with lessons, tutoring, or checkout.
    }
  }
}


function reportDashboardVital(metric: Vital) {
  if (typeof window === "undefined") return;
  // Honor explicit browser privacy signals as a further safeguard.
  if (navigator.doNotTrack === "1" || (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true) return;
  recordPublicVital(metric);
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
  useEffect(() => {
    const onHidden = () => { if (document.visibilityState === "hidden") flushPublicVitals(); };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", flushPublicVitals);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", flushPublicVitals);
    };
  }, []);
  return null;
}
