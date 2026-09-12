import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const target = (__ENV.STAGING_TARGET_URL || "").replace(/\/$/, "");
if (!target) {
  throw new Error("STAGING_TARGET_URL is required.");
}

const parsed = new URL(target);
if (parsed.protocol !== "https:") {
  throw new Error("Staging performance smoke must target HTTPS.");
}
if (parsed.username || parsed.password) {
  throw new Error("Do not place credentials in STAGING_TARGET_URL.");
}

const failures = new Rate("amaris_smoke_failures");
const serverErrors = new Rate("amaris_smoke_5xx");

export const options = {
  vus: Number(__ENV.STAGING_SMOKE_VUS || 20),
  duration: __ENV.STAGING_SMOKE_DURATION || "45s",
  thresholds: {
    amaris_smoke_failures: ["rate<=0.01"],
    amaris_smoke_5xx: ["rate<=0.005"],
    http_req_duration: ["p(95)<=1500", "p(99)<=3000"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
};

const paths = ["/", "/courses", "/login", "/register"];

export default function stagingSmokeJourney() {
  const path = paths[Math.floor(Math.random() * paths.length)];
  const response = http.get(`${target}${path}`, {
    redirects: 5,
    tags: { endpoint: path },
    timeout: "10s",
  });

  const ok = check(response, {
    "staging response is successful": (res) => res.status >= 200 && res.status < 400,
  });

  failures.add(!ok);
  serverErrors.add(response.status >= 500 && response.status <= 599);
  sleep(1);
}
