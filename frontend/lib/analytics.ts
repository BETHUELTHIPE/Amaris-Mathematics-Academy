export type AnalyticsUnit = "count" | "cents" | "hours";
export type ChartType = "line" | "bar" | "pie" | "gauge";
export type AnalyticsMetric = {
  key: string; title: string; unit: AnalyticsUnit; description: string; total: number;
  series: { date: string; value: number }[];
  breakdown: { label: string; value: number }[];
};
export type AnalyticsData = {
  version: 1; role: "student" | "tutor";
  period: { days: 7 | 30 | 90; start: string; end: string; timezone: string };
  generated_at: string; metrics: AnalyticsMetric[];
  progress: { title: string; percent: number; completed: number; total: number; description: string };
};

export const chartTypes: { key: ChartType; label: string }[] = [
  { key: "line", label: "Line" }, { key: "bar", label: "Bar" },
  { key: "pie", label: "Pie" }, { key: "gauge", label: "Gauge" },
];

export function analyticsDays(value?: string): 7 | 30 | 90 {
  return value === "7" ? 7 : value === "90" ? 90 : 30;
}

export function formatMetric(value: number, unit: AnalyticsUnit, compact = false): string {
  if (unit === "cents") return new Intl.NumberFormat("en-ZA", {
    style: "currency", currency: "ZAR", maximumFractionDigits: compact ? 1 : 2,
    ...(compact ? { notation: "compact" } : {}),
  }).format(value / 100);
  const result = new Intl.NumberFormat("en-ZA", {
    maximumFractionDigits: unit === "hours" ? 2 : 0,
    ...(compact ? { notation: "compact" } : {}),
  }).format(value);
  return unit === "hours" ? `${result} h` : result;
}

export function dateLabel(date: string): string {
  return new Intl.DateTimeFormat("en-ZA", { day: "numeric", month: "short", timeZone: "Africa/Johannesburg" })
    .format(new Date(`${date}T12:00:00Z`));
}

export function groupedSeries(series: AnalyticsMetric["series"]): { label: string; value: number }[] {
  const size = series.length > 14 ? 7 : 1;
  const rows = [];
  for (let index = 0; index < series.length; index += size) {
    const group = series.slice(index, index + size);
    rows.push({ label: group.length > 1 ? `${dateLabel(group[0].date)}–${dateLabel(group.at(-1)!.date)}` : dateLabel(group[0].date), value: group.reduce((sum, item) => sum + item.value, 0) });
  }
  return rows;
}

function csvCell(value: string | number): string {
  let text = String(value);
  if (/^[=+@\-\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function analyticsCsv(data: AnalyticsData): string {
  const rows: (string | number)[][] = [["Metric", "Date / category", "Value", "Unit"]];
  for (const metric of data.metrics) {
    for (const item of metric.series) rows.push([metric.title, item.date, metric.unit === "cents" ? (item.value / 100).toFixed(2) : item.value, metric.unit === "cents" ? "ZAR" : metric.unit]);
  }
  return "\uFEFF" + rows.map(row => row.map(csvCell).join(",")).join("\r\n");
}

export function validateAnalytics(value: unknown, role: AnalyticsData["role"]): AnalyticsData {
  if (!value || typeof value !== "object") throw new Error("Analytics unavailable.");
  const data = value as AnalyticsData;
  const validNumber = (n: unknown) => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= Number.MAX_SAFE_INTEGER;
  if (data.version !== 1 || data.role !== role || !data.period || ![7, 30, 90].includes(data.period.days)
    || data.period.timezone !== "Africa/Johannesburg" || !Number.isFinite(Date.parse(data.generated_at))
    || !Array.isArray(data.metrics) || data.metrics.length !== 4 || new Set(data.metrics.map(m => m.key)).size !== 4
    || !data.progress || !validNumber(data.progress.percent) || data.progress.percent > 100
    || !validNumber(data.progress.completed) || !validNumber(data.progress.total)
    || data.progress.completed > data.progress.total || typeof data.progress.title !== "string"
    || typeof data.progress.description !== "string"
    || !Number.isFinite(Date.parse(data.period.start)) || !Number.isFinite(Date.parse(data.period.end))) throw new Error("Analytics unavailable.");
  for (const metric of data.metrics) {
    if (!/^[a-z_]+$/.test(metric.key) || typeof metric.title !== "string" || typeof metric.description !== "string"
      || !["count", "cents", "hours"].includes(metric.unit) || !validNumber(metric.total)
      || !Array.isArray(metric.series) || metric.series.length !== data.period.days || !Array.isArray(metric.breakdown)
      || metric.breakdown.length > 12 || metric.series.some((p, i) => !/^\d{4}-\d{2}-\d{2}$/.test(p.date) || !validNumber(p.value) || (i > 0 && p.date <= metric.series[i - 1].date))
      || metric.series[0].date !== data.period.start || metric.series.at(-1)!.date !== data.period.end
      || metric.breakdown.some(p => typeof p.label !== "string" || !validNumber(p.value))
      || Math.abs(metric.series.reduce((sum, p) => sum + p.value, 0) - metric.total) > 0.011
      || Math.abs(metric.breakdown.reduce((sum, p) => sum + p.value, 0) - metric.total) > 0.011) throw new Error("Analytics unavailable.");
  }
  return {
    version: 1, role: data.role,
    period: { days: data.period.days, start: data.period.start, end: data.period.end, timezone: data.period.timezone },
    generated_at: data.generated_at,
    metrics: data.metrics.map(m => ({ key: m.key, title: m.title, unit: m.unit, description: m.description, total: m.total,
      series: m.series.map(p => ({ date: p.date, value: p.value })), breakdown: m.breakdown.map(p => ({ label: p.label, value: p.value })) })),
    progress: { title: data.progress.title, percent: data.progress.percent, total: data.progress.total, completed: data.progress.completed, description: data.progress.description },
  };
}
