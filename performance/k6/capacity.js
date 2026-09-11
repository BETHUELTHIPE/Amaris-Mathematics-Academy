import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const target = (__ENV.CAPACITY_TARGET_URL || "").replace(/\/$/, "");
if (!target) {
  throw new Error("CAPACITY_TARGET_URL is required.");
}

const allowedHosts = (__ENV.CAPACITY_ALLOWED_HOSTS || "localhost,127.0.0.1")
  .split(",")
  .map((value) => value.trim().toLowerCase())
  .filter(Boolean);
const parsedTarget = new URL(target);
const productionAllowed = (__ENV.CAPACITY_ALLOW_PRODUCTION || "false").toLowerCase() === "true";
const environmentName = (__ENV.CAPACITY_ENVIRONMENT || "staging").toLowerCase();
const knownProductionHosts = new Set([
  "amaris-mathematics-academy.bethuelthipe.chatgpt.site",
]);

if (!["http:", "https:"].includes(parsedTarget.protocol)) {
  throw new Error("CAPACITY_TARGET_URL must use http or https.");
}
if (parsedTarget.username || parsedTarget.password) {
  throw new Error("Do not place credentials in CAPACITY_TARGET_URL.");
}
if (allowedHosts.length && !allowedHosts.includes(parsedTarget.hostname.toLowerCase())) {
  throw new Error(`Target host ${parsedTarget.hostname} is not in CAPACITY_ALLOWED_HOSTS.`);
}
if ((environmentName === "production" || knownProductionHosts.has(parsedTarget.hostname.toLowerCase())) && !productionAllowed) {
  throw new Error("Production capacity testing requires explicit authorisation.");
}

const vus = Number(__ENV.CAPACITY_USERS || 100);
const duration = __ENV.CAPACITY_DURATION || "5m";
const ramp = __ENV.CAPACITY_RAMP || "1m";
const thinkSeconds = Number(__ENV.CAPACITY_THINK_SECONDS || 1);
const maxFailureRate = Number(__ENV.CAPACITY_MAX_FAILURE_RATE || 0.01);
const max5xxRate = Number(__ENV.CAPACITY_MAX_5XX_RATE || 0.005);
const p95Ms = Number(__ENV.CAPACITY_P95_MS || 1500);
const p99Ms = Number(__ENV.CAPACITY_P99_MS || 3000);

const supportedSteps = new Set([100, 500, 1000, 2500, 5000, 10000, 25000, 50000]);
if (!supportedSteps.has(vus)) {
  throw new Error("CAPACITY_USERS must be one of: 100, 500, 1000, 2500, 5000, 10000, 25000, 50000.");
}

export const failures = new Rate("amaris_failures");
export const serverErrors = new Rate("amaris_5xx");
export const requests = new Counter("amaris_requests");
export const responseTimes = new Trend("amaris_response_time", true);

export const options = {
  scenarios: {
    capacity: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: ramp, target: vus },
        { duration, target: vus },
        { duration: ramp, target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  thresholds: {
    amaris_failures: [`rate<=${maxFailureRate}`],
    amaris_5xx: [`rate<=${max5xxRate}`],
    http_req_duration: [`p(95)<=${p95Ms}`, `p(99)<=${p99Ms}`],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

const paths = [
  "/",
  "/courses",
  "/courses?search=algebra",
  "/login",
  "/register",
];

export default function () {
  const path = paths[Math.floor(Math.random() * paths.length)];
  const response = http.get(`${target}${path}`, {
    redirects: 0,
    tags: { endpoint: path },
  });
  const ok = check(response, {
    "status is acceptable": (res) => [200, 301, 302, 303, 307, 308].includes(res.status),
  });

  requests.add(1);
  responseTimes.add(response.timings.duration);
  failures.add(!ok);
  serverErrors.add(response.status >= 500 && response.status <= 599);
  sleep(thinkSeconds);
}

export function handleSummary(data) {
  const metric = (name) => data.metrics[name] || {};
  const httpDuration = metric("http_req_duration").values || {};
  const requestRate = (metric("http_reqs").values || {}).rate || 0;
  const failureRate = (metric("amaris_failures").values || {}).rate || 0;
  const fiveXxRate = (metric("amaris_5xx").values || {}).rate || 0;

  const summary = {
    capacity_users: vus,
    target_host: parsedTarget.hostname,
    environment: environmentName,
    rps: requestRate,
    p50_ms: httpDuration.med ?? null,
    p90_ms: httpDuration["p(90)"] ?? null,
    p95_ms: httpDuration["p(95)"] ?? null,
    p99_ms: httpDuration["p(99)"] ?? null,
    failure_percent: failureRate * 100,
    http_5xx_percent: fiveXxRate * 100,
    thresholds_passed: Object.values(data.root_group?.checks || {}).every((value) => value.fails === 0),
    note: "Infrastructure CPU/RAM/PostgreSQL/Redis/Gunicorn/Celery metrics must be captured from staging monitoring for the same test window.",
  };

  return {
    stdout: `${JSON.stringify(summary, null, 2)}\n`,
    [__ENV.CAPACITY_SUMMARY_FILE || `performance/reports/k6-${vus}.json`]: JSON.stringify(summary, null, 2),
  };
}
