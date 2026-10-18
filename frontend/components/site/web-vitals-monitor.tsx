"use client";

import { useReportWebVitals } from "next/web-vitals";
import { groupDevice, groupPage, type VitalPayload, validVital } from "@/lib/web-vitals";

// One small sample per browser page load; avoid repeated observers and
// network traffic from every render. No persistent user identifier or cookie.
const SAMPLE_RATE = 0.20;
let sampled: boolean | null = null;

function capture(metric: { name: string; value: number; id: string }) {
  if (typeof window === "undefined") return;
  if (sampled === null) sampled = Math.random() < SAMPLE_RATE;
  if (!sampled || !["LCP", "INP", "CLS"].includes(metric.name)) return;

  const payload: VitalPayload = {
    name: metric.name as VitalPayload["name"],
    value: metric.value,
    id: metric.id,
    page: groupPage(window.location.pathname),
    device: groupDevice(window.innerWidth),
  };
  if (!validVital(payload)) return;
  const body = JSON.stringify(payload);
  const target = "/api/web-vitals";
  try {
    if (navigator.sendBeacon?.(target, new Blob([body], { type: "application/json" }))) return;
    void fetch(target, {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      cache: "no-store",
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Real-user analytics must never break booking, teaching or checkout.
  }
}

export function WebVitalsMonitor() {
  useReportWebVitals(capture);
  return null;
}
