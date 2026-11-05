// One multipart checkout per distinct student, synchronized across generators.
import http from 'k6/http';
import { sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { vu } from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';
import { burstConfig, checkoutKey, validCheckout, validateStudents } from './video_burst_config.mjs';

const config = burstConfig(__ENV);
const students = new SharedArray('video-burst-students', () =>
  validateStudents(JSON.parse(open(config.studentsFile)), config.target));
const document = open('./fixtures/video-load.pdf', 'b');
const submissions = new Counter('video_submissions');
const valid = new Rate('video_checkout_valid');
const startOffset = new Trend('video_submission_start_offset_ms');

export const options = {
  scenarios: {
    video_submission_burst: {
      executor: 'per-vu-iterations',
      vus: config.target,
      iterations: 1,
      maxDuration: '30m',
      gracefulStop: '0s',
    },
  },
  maxRedirects: 0,
  thresholds: {
    video_submissions: ['count>0'], // Global exact coverage is checked after merging shard logs.
    video_checkout_valid: ['rate==1'],
    video_submission_start_offset_ms: ['min>=0', 'max<=1000'],
    http_req_failed: ['rate<=0.01'],
    http_req_duration: ['p(95)<=1000', 'p(99)<=2000'],
  },
};

export function setup() {
  const ahead = config.releaseAt - Date.now();
  if (ahead < 30_000 || ahead > 25 * 60_000) {
    throw new Error('The shared release time must be 30 seconds to 25 minutes ahead when each generator starts.');
  }
  return {};
}

export default function () {
  // idInTest is globally unique with matching k6 execution segment sequences.
  const student = students[vu.idInTest - 1];
  if (!student) throw new Error('Execution segment has no matching student identity.');
  const data = {
    programme: 'caps',
    subject: 'mathematics',
    level: 'Grade 12',
    topic: 'Synthetic capacity test',
    request_type: 'chapter_topic',
    instructions: 'Synthetic capacity request; do not fulfil or send notifications.',
    explanation_style: 'Worked examples',
    preferred_duration_minutes: '60',
    idempotency_key: checkoutKey(config, student),
    documents: http.file(document, 'capacity-test.pdf', 'application/pdf'),
  };
  const params = {
    headers: { Authorization: `Bearer ${student.access_token}` },
    tags: { name: 'Student video checkout' },
    redirects: 0,
    timeout: '30s',
  };
  const waitMs = config.releaseAt - Date.now();
  if (waitMs > 0) sleep(waitMs / 1000);
  const started = Date.now();
  startOffset.add(started - config.releaseAt);
  const response = http.post(`${config.origin}/api/v1/student/video-requests/checkout/`, data, params);
  const finished = Date.now();
  let accepted = false;
  try {
    accepted = response.status === 201 && Boolean(validCheckout(response.json(), config, student));
  } catch (_) {
    // Do not log bearer tokens, response bodies, payment fields or student data.
  }
  submissions.add(1);
  valid.add(accepted);
  // No tokens, student UUIDs, email addresses or payment payloads in evidence.
  console.log(`VIDEO_SUBMISSION|${config.runId}|${config.deployedSha}|${vu.idInTest}|${started}|${finished}|${accepted ? 1 : 0}|${response.status}`);
}
