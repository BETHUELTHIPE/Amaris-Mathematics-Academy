import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { requestAllowed, validateSyntheticAccount } from './production-request-policy.mjs';

// Use the browser dependency already pinned in the existing pa11y lock tree.
const require = createRequire(import.meta.url);
const pa11yRequire = createRequire(require.resolve('pa11y'));
const puppeteer = pa11yRequire('puppeteer');

const base = new URL(process.env.PRODUCTION_URL);
assert.equal(base.protocol, 'https:');
assert.equal(base.username + base.password + base.search + base.hash, '');
assert.equal(base.pathname, '/');
const course = process.env.PRODUCTION_COURSE_PATH;
const lesson = process.env.PRODUCTION_LESSON_PATH;
assert.match(course ?? '', /^\/courses\/[a-z0-9-]+$/);
assert.match(lesson ?? '', /^\/[a-zA-Z0-9/_-]+$/);
assert.ok(lesson !== course && !['/dashboard', '/login', '/register'].includes(lesson));
assert.ok(process.env.PRODUCTION_STUDENT_EMAIL && process.env.PRODUCTION_STUDENT_PASSWORD);
validateSyntheticAccount(process.env.PRODUCTION_STUDENT_EMAIL);

let browser;
let phase = 'browser-start';
try {
  browser = await puppeteer.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setBypassServiceWorker(true);
  await page.setCacheEnabled(false);
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(20000);
  await page.setRequestInterception(true);
  let allowLogin = false;
  let blockedMutation = false;
  page.on('request', (request) => {
    const allowed = requestAllowed(request.url(), request.method(), request.resourceType(), { base, course, lesson, allowLogin });
    if (!allowed) {
      if (!['GET', 'HEAD'].includes(request.method())) blockedMutation = true;
      void request.abort();
    } else {
      if (request.method() === 'POST') allowLogin = false;
      void request.continue();
    }
  });
  async function visit(path) {
    const response = await page.goto(new URL(path, base).href, { waitUntil: 'domcontentloaded' });
    assert.ok(response?.ok());
    assert.equal(new URL(page.url()).origin, base.origin);
    return new URL(page.url()).pathname;
  }
  phase = 'public-smoke';
  for (const path of ['/', '/courses', '/login', course]) {
    assert.equal(await visit(path), path);
    assert.ok(await page.$('main h1'));
  }
  phase = 'anonymous-access-denied';
  assert.equal(await visit('/dashboard'), '/login');
  assert.equal(await visit(lesson), '/login');
  phase = 'student-login';
  await visit('/login');
  await page.type('input[name="email"]', process.env.PRODUCTION_STUDENT_EMAIL);
  await page.type('input[name="password"]', process.env.PRODUCTION_STUDENT_PASSWORD);
  allowLogin = true;
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('form button[type="submit"]'),
  ]);
  allowLogin = false;
  assert.equal(new URL(page.url()).origin, base.origin);
  assert.equal(new URL(page.url()).pathname, '/dashboard');
  const state = await page.evaluate(async () => {
    const response = await fetch('/api/auth-state', { cache: 'no-store' });
    if (!response.ok) throw new Error('Auth state unavailable');
    return response.json();
  });
  assert.equal(state.authenticated, true);
  assert.equal(state.emailVerified, true);
  assert.ok(await page.$('nav[aria-label="Dashboard navigation"]'));
  phase = 'course-and-entitled-lesson';
  assert.equal(await visit(course), course);
  assert.equal(await visit(lesson), lesson);
  // A login page, empty shell or HTTP 200 error page must never count as learning access.
  await page.waitForSelector('[data-testid="lesson-content"]', { visible: true });
  const content = await page.$eval('[data-testid="lesson-content"]', element => element.textContent.trim());
  assert.ok(content.length > 20);
  assert.equal(blockedMutation, false, 'An unexpected write was blocked');
  console.log('Production public smoke and verified student learning journey passed.');
} catch {
  // Do not upload screenshots, traces, account data, DOM, cookies or exception text.
  console.error(`Production student journey failed at: ${phase}`);
  process.exitCode = 1;
} finally {
  await browser?.close();
}
