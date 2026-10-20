"use client";

import { useEffect } from "react";

/** No full URLs, identities, query parameters, events, or IP addresses leave the browser. */
type RecordName = "LCP" | "INP" | "CLS";
type RouteGroup = "home" | "courses" | "contact" | "announcements" | "matric" | "booking" | "student" | "other-public";
type DeviceGroup = "mobile" | "tablet" | "desktop";
type NetworkGroup = "slow-2g" | "2g" | "3g" | "4g" | "unknown";

type ConnectionNavigator = Navigator & {
  globalPrivacyControl?: boolean;
  connection?: { effectiveType?: string };
};

function safeRoute(path: string): RouteGroup | null {
  // Payment/identity screens must never be included, even as group labels.
  if (/\/(checkout|payment|invoice|orders|profile|security|login|register|auth|reset|password)(\/|$)/i.test(path)) {
    return null;
  }
  if (path === "/") return "home";
  if (path === "/courses" || path.startsWith("/courses/")) return "courses";
  if (path === "/contact") return "contact";
  if (path === "/announcements" || path.startsWith("/announcements/")) return "announcements";
  if (path.startsWith("/matric-upgrades")) return "matric";
  if (path === "/book-online-live-class") return "booking";
  if (path.startsWith("/student/") || path.startsWith("/dashboard")) return "student";
  // Ignore unidentified routes by default rather than risk leaking a secret path.
  return null;
}

function deviceGroup(): DeviceGroup {
  const width = window.innerWidth;
  return width <= 600 ? "mobile" : width <= 1024 ? "tablet" : "desktop";
}

function networkGroup(): NetworkGroup {
  const nav = navigator as ConnectionNavigator;
  const network = nav.connection?.effectiveType;
  if (network === "slow-2g" || network === "2g" || network === "3g" || network === "4g") return network;
  return "unknown";
}

function publish(name: RecordName, value: number, route: RouteGroup, device: DeviceGroup, network: NetworkGroup) {
  if (!Number.isFinite(value) || value < 0) return;
  const record = { name, value: Math.round(value * 1000) / 1000, route, device, network };
  // Do not send referrers, cookies or an identifiable per-navigation metric ID.
  try {
    void fetch("/api/field-vitals", {
      method: "POST",
      credentials: "omit",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ records: [record] }),
    }).catch(() => undefined);
  } catch {
    // Monitoring must never affect the student's learning experience.
  }
}

export function AnonymousWebVitals() {
  useEffect(() => {
    // Disabled until both Render services have the same server-only key.
    if (process.env.NEXT_PUBLIC_ENABLE_WEB_VITALS !== "true") return;
    const nav = navigator as ConnectionNavigator;
    if (nav.doNotTrack === "1" || nav.globalPrivacyControl === true) return;
    const state = window as Window & { __amarisVitalsStarted?: boolean };
    if (state.__amarisVitalsStarted || Math.random() >= 0.2) return;
    const route = safeRoute(window.location.pathname);
    if (!route) return;
    const device = deviceGroup();
    const network = networkGroup();
    const begin = () => {
      // Deferred to idle so this measurement doesn't harm first paint.
      void import("web-vitals").then(({ onLCP, onINP, onCLS }) => {
        onLCP((metric) => publish("LCP", metric.value, route, device, network));
        onINP((metric) => publish("INP", metric.value, route, device, network));
        onCLS((metric) => publish("CLS", metric.value, route, device, network));
      }).catch(() => undefined);
    };
    const scheduled = window.setTimeout(begin, 500);
    return () => window.clearTimeout(scheduled);
  }, []);
  return null;
}
