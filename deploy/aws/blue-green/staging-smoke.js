import http from 'k6/http';
import { check, sleep } from 'k6';

const base = 'https://16.171.164.5';
export const options = {
  scenarios: {
    bounded_staging_smoke: {
      executor: 'ramping-vus', startVUs: 0,
      stages: [{ duration: '15s', target: 5 }, { duration: '30s', target: 20 },
        { duration: '30s', target: 20 }, { duration: '15s', target: 0 }],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '15s' }],
    'http_req_duration{route:bootstrap}': [{ threshold: 'p(95)<500', abortOnFail: true, delayAbortEval: '30s' }],
    checks: ['rate>0.99'],
  },
};
export default function () {
  const home = http.get(base + '/', { tags: { route: 'homepage' }, redirects: 0, timeout: '10s' });
  check(home, { 'homepage 200': r => r.status === 200, 'via ALB': r => r.headers['X-Amaris-Network'] === 'public-alb' });
  const api = http.get(base + '/api/v1/bootstrap/', { tags: { route: 'bootstrap' }, redirects: 0, timeout: '10s' });
  check(api, { 'bootstrap 200': r => r.status === 200,
    'valid bootstrap': r => { try { return Object.prototype.hasOwnProperty.call(r.json(), 'settings'); } catch (_) { return false; } } });
  sleep(1);
}
