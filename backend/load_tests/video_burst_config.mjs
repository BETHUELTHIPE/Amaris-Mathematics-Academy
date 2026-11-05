// Pure configuration shared by k6 and the offline contract tests.
export const VIDEO_SUBMISSION_TARGET = 50_000;
const LIVE_HOSTS = new Set([
  'amaris-production-web.onrender.com',
  'amaris-mathematics-academy-live-students.onrender.com',
  'amaris-mathematics-academy.bethuelthipe.chatgpt.site',
]);

export function burstConfig(env) {
  const target = Number(env.VIDEO_LOAD_USERS || VIDEO_SUBMISSION_TARGET);
  if (!Number.isInteger(target) || target < 1 || target > VIDEO_SUBMISSION_TARGET) {
    throw new Error('VIDEO_LOAD_USERS must be an integer from 1 through 50000.');
  }
  if (!['local', 'staging', 'capacity'].includes(env.LOADTEST_ENVIRONMENT)) {
    throw new Error('Choose an isolated local, staging or capacity environment.');
  }
  const match = /^(https?):\/\/([a-z0-9.-]+)(?::([0-9]{1,5}))?\/?$/i.exec(env.LOADTEST_TARGET_URL || '');
  if (!match || (match[3] && (Number(match[3]) < 1 || Number(match[3]) > 65535))) {
    throw new Error('LOADTEST_TARGET_URL must be an HTTP(S) origin without credentials or a path.');
  }
  const hostname = match[2].toLowerCase().replace(/\.$/, '');
  const local = ['localhost', '127.0.0.1'].includes(hostname);
  if ((env.LOADTEST_ENVIRONMENT === 'local') !== local || (!local && match[1] !== 'https')) {
    throw new Error('Remote capacity targets require HTTPS; local mode requires a loopback host.');
  }
  const allowed = (env.LOADTEST_ALLOWED_HOSTS || '').toLowerCase().split(',').map(s => s.trim());
  if (!allowed.includes(hostname) || LIVE_HOSTS.has(hostname) || hostname.endsWith('payfast.co.za')) {
    throw new Error('Use an explicitly allowlisted isolated application host. Live Amaris and PayFast are blocked.');
  }
  if (env.PAYFAST_MODE !== 'sandbox' || env.VIDEO_LOAD_ISOLATION_CONFIRMED !== 'true') {
    throw new Error('Verify isolated database/storage, sandbox payments and disabled outbound notifications first.');
  }
  if (!/^[0-9a-f]{40}$/i.test(env.VIDEO_LOAD_DEPLOYED_SHA || '')) {
    throw new Error('VIDEO_LOAD_DEPLOYED_SHA must record the exact deployed revision.');
  }
  if (!/^[A-Za-z0-9_-]{1,20}$/.test(env.VIDEO_LOAD_RUN_ID || '')) {
    throw new Error('VIDEO_LOAD_RUN_ID must contain 1–20 letters, digits, underscores or hyphens.');
  }
  const releaseAt = Number(env.VIDEO_LOAD_RELEASE_AT_MS);
  if (!Number.isSafeInteger(releaseAt) || releaseAt <= 0) {
    throw new Error('Set one shared future VIDEO_LOAD_RELEASE_AT_MS on every generator.');
  }
  if (!env.VIDEO_LOAD_STUDENTS_FILE) throw new Error('A private test-student manifest is required.');
  return {
    target,
    origin: env.LOADTEST_TARGET_URL.replace(/\/$/, ''),
    releaseAt,
    runId: env.VIDEO_LOAD_RUN_ID,
    deployedSha: env.VIDEO_LOAD_DEPLOYED_SHA.toLowerCase(),
    studentsFile: env.VIDEO_LOAD_STUDENTS_FILE,
  };
}

export function validateStudents(data, target) {
  if (!Array.isArray(data.students) || data.students.length !== target) {
    throw new Error('Provide exactly one distinct test student and access token per target user.');
  }
  const ids = new Set();
  const tokens = new Set();
  for (const student of data.students) {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(student.student_id || '')) {
      throw new Error('Each test student needs a UUID.');
    }
    const id = student.student_id.toLowerCase();
    const token = student.access_token;
    if (typeof token !== 'string' || !token.trim() || /\s/.test(token) || ids.has(id) || tokens.has(token)) {
      throw new Error('Test student identities and nonempty bearer tokens must be unique.');
    }
    ids.add(id);
    tokens.add(token);
  }
  return data.students;
}

export function checkoutKey(config, student) {
  return `vload-${config.runId}-${student.student_id.replace(/-/g, '').toLowerCase()}`;
}

export function validCheckout(response, config, student) {
  const reference = `VRQ-${checkoutKey(config, student)}`;
  return response && response.request_reference === reference && response.status === 'pending_payment'
    && response.gateway_url === 'https://sandbox.payfast.co.za/eng/process'
    && response.fields && response.fields.amount === '450.00'
    && response.fields.m_payment_id === reference
    && typeof response.fields.custom_str1 === 'string'
    && response.fields.custom_str1.toLowerCase() === student.student_id.toLowerCase()
    && /^[0-9a-f]{32}$/i.test(response.fields.signature || '');
}
