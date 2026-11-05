"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Activity, ArrowDownToLine, BarChart3, Check, ChevronDown, CircleGauge, LineChart, LockKeyhole, PieChart, RefreshCw, Target, TrendingUp } from "lucide-react";
import { analyticsCsv, chartTypes, dateLabel, formatMetric, groupedSeries, type AnalyticsData, type AnalyticsMetric, type ChartType } from "@/lib/analytics";
import "./analytics-dashboard.css";

const COLORS = ["#205bd7", "#0b837a", "#c08719", "#8655c6"];
const memory = new Map<string, string>();
const PREF_EVENT = "amaris-analytics-preferences";
type Preferences = { chart?: ChartType; goals?: Record<string, number> };

function usePreferences(key: string) {
  const subscribe = useCallback((listener: () => void) => {
    const external = (event: StorageEvent) => { if (event.key === key) { memory.set(key, event.newValue || ""); listener(); } };
    window.addEventListener(PREF_EVENT, listener);
    window.addEventListener("storage", external);
    return () => { window.removeEventListener(PREF_EVENT, listener); window.removeEventListener("storage", external); };
  }, [key]);
  const snapshot = useCallback(() => {
    if (memory.has(key)) return memory.get(key)!;
    try { return window.localStorage.getItem(key) || ""; } catch { return ""; }
  }, [key]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => "");
  const value = useMemo<Preferences>(() => {
    try {
      const saved = JSON.parse(raw) as Preferences;
      return { chart: chartTypes.some(item => item.key === saved.chart) ? saved.chart : "line", goals: saved.goals && typeof saved.goals === "object" ? saved.goals : {} };
    } catch { return { chart: "line", goals: {} }; }
  }, [raw]);
  function save(next: Preferences) {
    const result = JSON.stringify(next);
    memory.set(key, result);
    try { window.localStorage.setItem(key, result); } catch { /* Charts still work when browser storage is blocked. */ }
    window.dispatchEvent(new Event(PREF_EVENT));
  }
  return [value, save] as const;
}

function Gauge({ percent, value, label, color = COLORS[1] }: { percent: number; value: string; label: string; color?: string }) {
  const ratio = Math.max(0, Math.min(100, percent));
  const angle = Math.PI * (1 - ratio / 100);
  return <svg className="an-gauge" viewBox="0 0 280 185" role="img" aria-label={`${label}: ${value}; ${Math.round(percent)} percent`}>
    <title>{label}: {value}</title>
    <path d="M 28 148 A 112 112 0 0 1 252 148" fill="none" stroke="#e7edf5" strokeWidth="19" strokeLinecap="round" />
    <path d="M 28 148 A 112 112 0 0 1 252 148" fill="none" stroke={color} strokeWidth="19" strokeLinecap="round" pathLength="100" strokeDasharray={`${ratio} 100`} />
    <text x="140" y="109" textAnchor="middle" className="an-gauge-value">{value}</text>
    <line x1="140" y1="148" x2={140 + Math.cos(angle) * 71} y2={148 - Math.sin(angle) * 71} stroke="#173553" strokeWidth="3" strokeLinecap="round" />
    <circle cx="140" cy="148" r="7" fill="#173553" />
    <text x="24" y="177" className="an-axis">0%</text><text x="226" y="177" className="an-axis">100%</text>
  </svg>;
}

function Timeline({ metric, chart }: { metric: AnalyticsMetric; chart: "line" | "bar" }) {
  const holder = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  const id = useId().replaceAll(":", "");
  useEffect(() => {
    if (!holder.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width)));
    observer.observe(holder.current);
    return () => observer.disconnect();
  }, []);
  const points = groupedSeries(metric.series);
  const largest = Math.max(1, ...points.map(point => point.value));
  const max = metric.unit === "count" ? Math.ceil(largest * 1.15 / 2) * 2 : largest * 1.15;
  const left = 74, right = width - 16, bottom = 224, top = 18;
  const slot = (right - left) / points.length;
  const x = (index: number) => left + slot * (index + 0.5);
  const y = (value: number) => bottom - value / max * (bottom - top);
  const line = points.map((point, index) => `${index ? "L" : "M"}${x(index)},${y(point.value)}`).join(" ");
  const tickEvery = Math.ceil(points.length / (width < 480 ? 3 : 5));
  return <div ref={holder} className="an-timeline">
    <div className="an-chart-tooltip" aria-live="polite">{active !== null && points[active] ? <><strong>{points[active].label}</strong><span>{formatMetric(points[active].value, metric.unit)}</span></> : <span>Hover or focus a point to explore</span>}</div>
    <svg viewBox={`0 0 ${width} 270`} role="img" aria-label={`${metric.title}, ${chart === "line" ? "line" : "bar"} chart. Daily totals are available in the data table.`}>
      <title>{metric.title}</title>
      <defs><linearGradient id={`area-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={COLORS[0]} stopOpacity=".18" /><stop offset="1" stopColor={COLORS[0]} stopOpacity=".01" /></linearGradient></defs>
      {[0, 0.5, 1].map(fraction => <g key={fraction}><line x1={left} x2={right} y1={y(max * fraction)} y2={y(max * fraction)} stroke="#e5ebf3" strokeDasharray={fraction ? "4 5" : undefined} /><text x={left - 12} y={y(max * fraction) + 4} textAnchor="end" className="an-axis">{formatMetric(max * fraction, metric.unit, true)}</text></g>)}
      {chart === "line" && <><path d={`${line} L${x(points.length - 1)},${bottom} L${x(0)},${bottom} Z`} fill={`url(#area-${id})`} /><path d={line} fill="none" stroke={COLORS[0]} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" /></>}
      {points.map((point, index) => <g key={point.label}>
        {chart === "bar" ? <rect x={x(index) - slot * .28} y={y(point.value)} width={Math.max(2, slot * .56)} height={Math.max(point.value > 0 ? 2 : 0, bottom - y(point.value))} rx="4" fill={active === index ? COLORS[1] : COLORS[0]} tabIndex={0} aria-label={`${point.label}: ${formatMetric(point.value, metric.unit)}`} onFocus={() => setActive(index)} onBlur={() => setActive(null)} onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}><title>{point.label}: {formatMetric(point.value, metric.unit)}</title></rect>
          : <circle cx={x(index)} cy={y(point.value)} r={active === index ? 6 : 4} fill="white" stroke={COLORS[0]} strokeWidth="2" tabIndex={0} aria-label={`${point.label}: ${formatMetric(point.value, metric.unit)}`} onFocus={() => setActive(index)} onBlur={() => setActive(null)} onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}><title>{point.label}: {formatMetric(point.value, metric.unit)}</title></circle>}
        {index % tickEvery === 0 && <text x={x(index)} y="251" textAnchor="middle" className="an-axis">{dateLabel(metric.series[Math.min(index * (metric.series.length > 14 ? 7 : 1), metric.series.length - 1)].date)}</text>}
      </g>)}
    </svg>
    <p className="an-chart-footnote">{metric.series.length > 14 ? "Weekly totals; the final week may be partial." : "Daily totals."} All dates are in South African time.</p>
  </div>;
}

function Mix({ metric }: { metric: AnalyticsMetric }) {
  return <div className="an-mix">
    <svg viewBox="0 0 260 260" role="img" aria-label={`${metric.title}: contribution by service. Exact amounts are listed alongside.`}>
      <title>{metric.title}: service mix</title>
      <circle cx="130" cy="130" r="95" fill="none" stroke="#e7edf5" strokeWidth="42" />
      {metric.breakdown.map((item, index) => {
        if (!item.value) return null;
        const percent = metric.total ? item.value / metric.total * 100 : 0;
        const begin = metric.total ? metric.breakdown.slice(0, index).reduce((sum, prior) => sum + prior.value, 0) / metric.total * 100 : 0;
        return <circle key={item.label} cx="130" cy="130" r="95" fill="none" stroke={COLORS[index % COLORS.length]} strokeWidth="42" pathLength="100" strokeDasharray={`${percent} ${100 - percent}`} strokeDashoffset={-begin} transform="rotate(-90 130 130)" tabIndex={0} aria-label={`${item.label}: ${formatMetric(item.value, metric.unit)}, ${percent.toFixed(1)} percent`}><title>{item.label}: {formatMetric(item.value, metric.unit)} ({percent.toFixed(1)}%)</title></circle>;
      })}
      <text x="130" y="125" textAnchor="middle" className="an-donut-value">{formatMetric(metric.total, metric.unit, true)}</text><text x="130" y="150" textAnchor="middle" className="an-axis">selected period</text>
    </svg>
    <ul className="an-legend">{metric.breakdown.map((item, index) => <li key={item.label}><span className="an-legend-dot" style={{ background: COLORS[index % COLORS.length] }} /><span>{item.label}<small>{metric.total ? `${(item.value / metric.total * 100).toFixed(1)}% of total` : "No recorded activity"}</small></span><strong>{formatMetric(item.value, metric.unit)}</strong></li>)}</ul>
  </div>;
}

export function AnalyticsUnavailable({ role }: { role: "student" | "tutor" }) {
  return <section className="an-dashboard an-unavailable" role="status"><Activity size={36} /><h2>Your analytics are temporarily unavailable</h2><p>We could not load your private {role} records. Refresh to try again. No estimates or sample figures are being shown.</p><button className="an-button" onClick={() => window.location.reload()}><RefreshCw size={16} /> Try again</button></section>;
}

export function AnalyticsDashboard({ data, preferenceScope }: { data: AnalyticsData; preferenceScope: string }) {
  const [metricKey, setMetricKey] = useState(data.metrics[0].key);
  const [prefs, save] = usePreferences(`amaris.analytics.v1:${data.role}:${preferenceScope}:${data.period.days}`);
  const metric = data.metrics.find(item => item.key === metricKey) || data.metrics[0];
  const view = prefs.chart || "line";
  const storedGoal = prefs.goals?.[metric.key];
  const goal = typeof storedGoal === "number" && Number.isFinite(storedGoal) && storedGoal > 0 ? storedGoal : null;
  const [exported, setExported] = useState(false);
  const path = data.role === "student" ? "/dashboard/analytics" : "/tutor/analytics";
  const updated = new Intl.DateTimeFormat("en-ZA", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Johannesburg" }).format(new Date(data.generated_at));
  function exportCsv() {
    const url = URL.createObjectURL(new Blob([analyticsCsv(data)], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `amaris-${data.role}-analytics-${data.period.days}days.csv`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000); setExported(true);
  }
  const icons = [TrendingUp, Activity, BarChart3, Check];
  return <div className="an-dashboard">
    <div className="an-toolbar"><div><span className="an-private"><LockKeyhole size={13} /> Only your records</span><p>{dateLabel(data.period.start)} – {dateLabel(data.period.end)} <span>· Updated {updated} SAST</span></p></div><div className="an-toolbar-actions"><nav className="an-periods" aria-label="Analytics date range">{[7, 30, 90].map(days => <a key={days} href={`${path}?days=${days}`} aria-current={data.period.days === days ? "page" : undefined}>{days} days</a>)}</nav><button className="an-button" onClick={exportCsv}><ArrowDownToLine size={16} /><span>{exported ? "Export again" : "Export CSV"}</span></button></div></div>
    <div className="an-kpis" aria-label="Your analytics summary">{data.metrics.map((item, index) => { const Icon = icons[index % icons.length]; return <button key={item.key} type="button" className={`an-kpi ${metric.key === item.key ? "an-kpi-active" : ""}`} aria-pressed={metric.key === item.key} onClick={() => setMetricKey(item.key)}><span className="an-kpi-top"><span>{item.title}</span><span className={`an-icon an-icon-${index}`}><Icon size={18} /></span></span><strong>{formatMetric(item.total, item.unit)}</strong><small>{data.period.days}-day total <span>{metric.key === item.key ? "Selected" : "Explore →"}</span></small></button>; })}</div>
    <div className="an-main-grid"><section className="an-panel an-explorer" aria-labelledby="an-explorer-title"><div className="an-panel-heading"><div><p className="an-eyebrow">Your analytics studio</p><h2 id="an-explorer-title">Make your progress visible.</h2></div><span className="an-live-dot">Private insights</span></div>
      <div className="an-explorer-controls"><label className="an-metric-select"><span>Metric</span><select value={metric.key} onChange={event => setMetricKey(event.target.value)}>{data.metrics.map(item => <option key={item.key} value={item.key}>{item.title}</option>)}</select><ChevronDown size={15} aria-hidden="true" /></label><div className="an-chart-switch" role="group" aria-label="Choose a visual">{chartTypes.map(({ key, label }) => { const Icon = { line: LineChart, bar: BarChart3, pie: PieChart, gauge: CircleGauge }[key]; return <button key={key} type="button" aria-pressed={view === key} onClick={() => save({ ...prefs, chart: key })}><Icon size={16} /><span>{label}</span></button>; })}</div></div>
      <div className="an-explorer-value"><strong>{formatMetric(metric.total, metric.unit)}</strong><span>{metric.title.toLowerCase()} in this period</span></div>
      {!metric.total && view !== "gauge" ? <div className="an-empty"><Activity size={32} /><h3>A clear starting point.</h3><p>No activity was recorded for this metric in the selected period. Your next recorded activity will appear here.</p></div> : view === "line" || view === "bar" ? <Timeline key={`${metric.key}:${view}`} metric={metric} chart={view} /> : view === "pie" ? <Mix metric={metric} /> : <div className="an-goal-visual">{goal ? <><Gauge percent={metric.total / goal * 100} value={`${Math.round(metric.total / goal * 100)}%`} label={`${metric.title}, your personal target`} /><p><strong>{formatMetric(metric.total, metric.unit)}</strong> of your <strong>{formatMetric(goal, metric.unit)}</strong> target</p>{metric.total > goal && <span className="an-goal-reached"><Check size={14} /> Target exceeded; the arc stops at 100%.</span>}</> : <div className="an-empty"><Target size={34} /><h3>A goal that belongs to you.</h3><p>Set your own target below to turn this metric into a gauge. We will not choose a financial or learning target for you.</p></div>}
        <form className="an-goal-form" onSubmit={event => { event.preventDefault(); const input = new FormData(event.currentTarget).get("target"); const parsed = Number(input); const value = metric.unit === "cents" ? Math.round(parsed * 100) : parsed; if (Number.isFinite(value) && value > 0 && value <= Number.MAX_SAFE_INTEGER) save({ ...prefs, goals: { ...prefs.goals, [metric.key]: value } }); }}><label htmlFor="an-personal-target">Your {data.period.days}-day target {metric.unit === "cents" ? "(ZAR)" : metric.unit === "hours" ? "(hours)" : "(services)"}</label><div><input key={`${metric.key}:${goal}`} id="an-personal-target" name="target" type="number" required min={metric.unit === "count" ? "1" : "0.01"} step={metric.unit === "count" ? "1" : "0.01"} defaultValue={goal ? (metric.unit === "cents" ? goal / 100 : goal) : ""} placeholder="Enter your target" /><button type="submit" className="an-button an-button-primary">Save target</button></div><small>Chart choices and targets stay in this browser. Your records remain unchanged.</small></form>
      </div>}
      <p className="an-definition">{metric.description}</p>
      <details className="an-data-table"><summary>View the exact daily data <ChevronDown size={15} /></summary><div tabIndex={0} role="region" aria-label={`${metric.title}, daily data`}><table><caption>{metric.title} · South African time · {metric.unit === "cents" ? "ZAR" : metric.unit}</caption><thead><tr><th scope="col">Date</th><th scope="col">Value</th></tr></thead><tbody>{metric.series.map(item => <tr key={item.date}><th scope="row">{dateLabel(item.date)}</th><td>{formatMetric(item.value, metric.unit)}</td></tr>)}</tbody></table></div></details>
    </section>
    <aside className="an-insights"><section className="an-panel an-progress"><div className="an-panel-heading"><div><p className="an-eyebrow">Every step counts</p><h2>{data.progress.title}</h2></div><span className="an-icon an-icon-1"><CircleGauge size={20} /></span></div>{data.progress.total ? <><Gauge percent={data.progress.percent} value={`${data.progress.percent}%`} label={data.progress.title} /><div className="an-progress-totals"><div><strong>{data.progress.completed}</strong><span>{data.role === "student" ? "courses completed" : "classes completed"}</span></div><div><strong>{data.progress.total}</strong><span>{data.role === "student" ? "current courses" : "past paid classes"}</span></div></div></> : <div className="an-empty an-empty-small"><CircleGauge size={32} /><h3>{data.role === "student" ? "Your next chapter starts here." : "Room to grow."}</h3><p>{data.role === "student" ? "Progress appears once you have a current course enrolment." : "A completion gauge appears once paid classes have ended in this period."}</p></div>}<p className="an-definition">{data.progress.description}</p></section>
      <section className="an-guidance"><span className="an-icon"><Target size={19} /></span><p className="an-eyebrow">Designed around you</p><h2>Your data.<br />Your perspective.</h2><p>Spot a trend with a line chart, compare totals with bars, explore the service mix with a pie, or track your own target with a gauge.</p><div><Check size={15} /> No comparisons with other people</div><div><Check size={15} /> No student identities in exports</div></section></aside></div>
    <p className="an-preference-note"><LockKeyhole size={13} /> Views are private to your verified account. Figures reflect recorded activity, not academic grades or guaranteed income.</p><span className="an-sr-only" role="status">{exported ? "Your analytics CSV is ready to download." : ""}</span>
  </div>;
}
