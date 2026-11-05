// Synthetic visual-test fixture only. Never imported by production routes.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { AnalyticsDashboard } from "@/components/site/analytics-dashboard";
import type { AnalyticsData } from "@/lib/analytics";
import "./analytics-preview.css";

export function fixture(role: "student" | "tutor", days: 7 | 30 | 90): AnalyticsData {
  const end = Date.UTC(2026, 10, 5);
  const dates = Array.from({ length: days }, (_, index) => new Date(end - (days - 1 - index) * 86400000).toISOString().slice(0, 10));
  const definitions = role === "student" ? [
    ["paid_services", "Paid learning services", "count"], ["spending", "Verified spending", "cents"],
    ["lesson_hours", "Scheduled lesson hours", "hours"], ["video_requests", "Video requests submitted", "count"],
  ] : [["earnings", "Recorded tutor earnings", "cents"], ["payouts", "Confirmed payouts", "cents"], ["lesson_hours", "Scheduled teaching hours", "hours"], ["videos_ready", "Video lessons ready", "count"]];
  const metrics = definitions.map(([key, title, rawUnit], metricIndex) => {
    const unit = rawUnit as "count" | "cents" | "hours";
    const series = dates.map((date, index) => ({ date, value: unit === "cents" ? (2 + ((index * 7 + metricIndex) % 6)) * (role === "tutor" ? 6500 : 2000) : (index + metricIndex * 2) % 5 }));
    const total = series.reduce((sum, point) => sum + point.value, 0);
    const first = Math.floor(total * .42), second = Math.floor(total * .36);
    return { key, title, unit, description: role === "tutor" ? "Recorded earnings include held amounts; only provider-confirmed payouts appear under payouts. Scheduled hours do not prove attendance." : "Private verified activity grouped in South African time. Cancelled or unverified payments are excluded from financial metrics.", total, series, breakdown: [{ label: "Courses", value: first }, { label: "Live classes", value: second }, { label: "Requested videos", value: total - first - second }] };
  });
  return { version: 1, role, period: { days, start: dates[0], end: dates.at(-1)!, timezone: "Africa/Johannesburg" }, generated_at: "2026-11-05T08:42:00Z", metrics,
    progress: { title: role === "student" ? "Your learning progress" : "Recorded class completion", percent: role === "student" ? 68 : 82, completed: role === "student" ? 3 : 23, total: role === "student" ? 8 : 28, description: role === "student" ? "Average saved progress across your current course enrolments. Independent of the date filter; this is not an exam result." : "Classes recorded as completed out of past paid classes in this period. Future sessions are excluded; attendance is not inferred." } };
}

function Preview() {
  const [role, setRole] = useState<"student" | "tutor">(window.location.pathname.startsWith("/tutor") ? "tutor" : "student");
  const raw = new URLSearchParams(window.location.search).get("days");
  const days = raw === "7" ? 7 : raw === "90" ? 90 : 30;
  return <><div className="preview-disclosure">DESIGN PREVIEW · SYNTHETIC DATA · NOT A LIVE ACCOUNT <div><button type="button" aria-pressed={role === "student"} onClick={() => { setRole("student"); window.history.replaceState(null, "", `/dashboard/analytics?days=${days}`); }}>Student view</button><button type="button" aria-pressed={role === "tutor"} onClick={() => { setRole("tutor"); window.history.replaceState(null, "", `/tutor/analytics?days=${days}`); }}>Tutor view</button></div></div><header className="preview-header"><a href="/" className="preview-brand"><b>A</b><span>AMARIS<small>MATHEMATICS ACADEMY</small></span></a><span className="preview-header-label">Your mathematics. Your momentum.</span><div className="preview-avatar">{role === "student" ? "ST" : "TU"}</div></header><div className="preview-layout"><aside className="preview-nav"><small>MY WORKSPACE</small><p>Overview</p><p>My courses</p><p className="preview-selected">▥ &nbsp; My analytics</p><p>My workflows</p><p>Orders &amp; payments</p><p>Notifications</p><div className="preview-nav-note">A little progress.<br /><strong>A bigger future.</strong><span>Built around your next step.</span></div></aside><main><div className="preview-page-heading"><p>{role === "student" ? "LEARNING INSIGHTS" : "TEACHING INSIGHTS"}</p><h1>{role === "student" ? "Your learning. A little clearer." : "Your impact, in perspective."}</h1><span>{role === "student" ? "A private view of your learning activity, with visuals that make sense to you." : "A clear view of your teaching activity and recorded earnings. Choose how you see it."}</span></div><AnalyticsDashboard data={fixture(role, days)} preferenceScope={`preview-${role}`} /></main></div></>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
