import assert from 'node:assert/strict';
import { test } from 'node:test';
import { burstConfig, checkoutKey, validCheckout, validateStudents, VIDEO_SUBMISSION_TARGET } from './video_burst_config.mjs';

const env = {
  LOADTEST_ENVIRONMENT: 'capacity',
  LOADTEST_TARGET_URL: 'https://isolated-capacity.example.test',
  LOADTEST_ALLOWED_HOSTS: 'isolated-capacity.example.test',
  PAYFAST_MODE: 'sandbox',
  VIDEO_LOAD_ISOLATION_CONFIRMED: 'true',
  VIDEO_LOAD_DEPLOYED_SHA: 'a'.repeat(40),
  VIDEO_LOAD_RUN_ID: 'contract-only',
  VIDEO_LOAD_RELEASE_AT_MS: '2000000000000',
  VIDEO_LOAD_STUDENTS_FILE: '/tmp/private-students.json',
};
function student(index) {
  return {
    student_id: `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`,
    access_token: `offline-contract-token-${index}`,
  };
}

test('default acceptance target is 50000, with exactly 50000 distinct identities and valid keys', () => {
  const config = burstConfig(env);
  assert.equal(VIDEO_SUBMISSION_TARGET, 50_000);
  assert.equal(config.target, 50_000);
  const students = Array.from({ length: config.target }, (_, index) => student(index));
  assert.equal(validateStudents({ students }, config.target).length, 50_000);
  const keys = new Set(students.map(item => checkoutKey(config, item)));
  assert.equal(keys.size, 50_000);
  for (const key of keys) assert.match(key, /^[A-Za-z0-9_-]{8,64}$/);
});

test('missing, duplicate, reused or malformed identities fail before any HTTP request', () => {
  for (const data of [
    {},
    { students: [student(0)] },
    { students: [student(0), student(0)] },
    { students: [student(0), { ...student(1), access_token: student(0).access_token }] },
    { students: [student(0), { ...student(1), student_id: 'bad-id' }] },
    { students: [student(0), { ...student(1), access_token: 'token with newline\n' }] },
  ]) assert.throws(() => validateStudents(data, 2));
});

test('production, payment gateways, unlisted targets and nonisolated runs are rejected', () => {
  for (const patch of [
    { LOADTEST_ENVIRONMENT: 'production' },
    { LOADTEST_TARGET_URL: 'https://amaris-production-web.onrender.com', LOADTEST_ALLOWED_HOSTS: 'amaris-production-web.onrender.com' },
    { LOADTEST_TARGET_URL: 'https://amaris-production-web.onrender.com.', LOADTEST_ALLOWED_HOSTS: 'amaris-production-web.onrender.com' },
    { LOADTEST_TARGET_URL: 'https://sandbox.payfast.co.za', LOADTEST_ALLOWED_HOSTS: 'sandbox.payfast.co.za' },
    { LOADTEST_ALLOWED_HOSTS: '' },
    { LOADTEST_TARGET_URL: 'http://isolated-capacity.example.test' },
    { LOADTEST_TARGET_URL: 'https://user:password@isolated-capacity.example.test' },
    { LOADTEST_TARGET_URL: 'https://isolated-capacity.example.test/path' },
    { LOADTEST_TARGET_URL: 'https://isolated-capacity.example.test:99999' },
    { VIDEO_LOAD_ISOLATION_CONFIRMED: 'false' },
    { PAYFAST_MODE: 'live' },
    { VIDEO_LOAD_DEPLOYED_SHA: 'main' },
    { VIDEO_LOAD_RUN_ID: 'too-long-run-id-that-would-break-the-idempotency-key' },
    { VIDEO_LOAD_RELEASE_AT_MS: '' },
    { VIDEO_LOAD_STUDENTS_FILE: '' },
    { VIDEO_LOAD_USERS: '50001' },
    { VIDEO_LOAD_USERS: '1.5' },
  ]) assert.throws(() => burstConfig({ ...env, ...patch }));
});

test('only a server-priced, signed sandbox checkout for the correct student counts as success', () => {
  const config = burstConfig(env);
  const identity = student(0);
  const reference = `VRQ-${checkoutKey(config, identity)}`;
  const response = {
    request_reference: reference,
    status: 'pending_payment',
    gateway_url: 'https://sandbox.payfast.co.za/eng/process',
    fields: { amount: '450.00', m_payment_id: reference, custom_str1: identity.student_id, signature: 'a'.repeat(32) },
  };
  assert.equal(validCheckout(response, config, identity), true);
  for (const patch of [
    { status: 'queued' },
    { request_reference: 'another-students-order' },
    { gateway_url: 'https://www.payfast.co.za/eng/process' },
    { fields: { ...response.fields, amount: '1.00' } },
    { fields: { ...response.fields, custom_str1: student(1).student_id } },
    { fields: { ...response.fields, custom_str1: undefined } },
    { fields: { ...response.fields, signature: '' } },
  ]) assert.equal(Boolean(validCheckout({ ...response, ...patch }, config, identity)), false);
});
