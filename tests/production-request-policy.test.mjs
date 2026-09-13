import assert from 'node:assert/strict';
import test from 'node:test';
import { requestAllowed, validateSyntheticAccount } from '../scripts/release/production-request-policy.mjs';

const config = { base: new URL('https://academy.example.test'), course: '/courses/synthetic', lesson: '/lessons/synthetic' };
const allowed = (path, method = 'GET', type = 'document', overrides = {}) =>
  requestAllowed(new URL(path, config.base).href, method, type, { ...config, ...overrides });

test('only intended read routes and local static assets are allowed', () => {
  for (const path of ['/', '/login', '/courses', '/dashboard', '/api/auth-state', config.course, config.lesson]) {
    assert.equal(allowed(path), true);
  }
  assert.equal(allowed('/assets/a.js', 'GET', 'script'), true);
  assert.equal(allowed('/_next/static/a.css', 'GET', 'stylesheet'), true);
  assert.equal(allowed('/courses?_rsc=abc', 'GET', 'fetch'), true);
});

test('all payment providers, same-origin writes and redirect escapes are blocked', () => {
  for (const path of ['/api/payments', '/checkout', '/register', '/api/progress', '/api/bookings', '/api/email']) {
    for (const method of ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']) assert.equal(allowed(path, method), false);
  }
  for (const url of ['https://www.payfast.co.za/eng/process', 'https://pay.google.com/', '//attacker.test/login']) {
    assert.equal(allowed(url, 'POST', 'document', { allowLogin: true }), false);
  }
  assert.equal(allowed('/assets/a.js?checkout=true', 'GET', 'script'), false);
  assert.equal(allowed('/api/payments/create.js', 'GET', 'script'), false);
  assert.equal(allowed('/login?redirect=https://attacker.test'), false);
  assert.equal(allowed('/courses?purchase=true'), false);
});

test('login POST is allowed only during the explicit login phase', () => {
  assert.equal(allowed('/login', 'POST'), false);
  assert.equal(allowed('/login', 'POST', 'document', { allowLogin: true }), true);
  assert.equal(allowed('/login?next=/checkout', 'POST', 'document', { allowLogin: true }), false);
  assert.equal(allowed('/dashboard', 'POST', 'fetch', { allowLogin: true }), false);
});

test('real or arbitrary account emails are rejected', () => {
  validateSyntheticAccount('synthetic-smoke@amaris.test');
  for (const email of ['', undefined, 'student@gmail.com', 'tutor@amaris.test']) {
    assert.throws(() => validateSyntheticAccount(email));
  }
});
