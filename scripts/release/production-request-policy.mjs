import assert from 'node:assert/strict';

// The only production write permitted by this browser is one intentional login.
// Payment, booking, registration, progress, email and all third-party requests
// are denied, including same-origin payment proxies and redirect destinations.
export function requestAllowed(rawUrl, method, resourceType, { base, course, lesson, allowLogin = false }) {
  let url;
  try { url = new URL(rawUrl); } catch { return false; }
  if (url.origin !== base.origin || url.username || url.password || url.hash) return false;
  if (/\/(?:checkout|payments?|payfast|bookings?|progress|register|logout)(?:\/|$)/i.test(url.pathname)) return false;
  if (method === 'POST') return allowLogin && url.pathname === '/login' && !url.search;
  if (!['GET', 'HEAD'].includes(method)) return false;
  const safePages = ['/', '/courses', '/login', '/dashboard', '/api/auth-state', course, lesson];
  if (safePages.includes(url.pathname)) {
    // Next server-component reads can carry only its cache-busting _rsc key.
    return [...url.searchParams.keys()].every(key => key === '_rsc' || (url.pathname === '/login' && key === 'next'));
  }
  if (url.search) return false;
  if (!/^\/[a-zA-Z0-9_./-]+$/.test(url.pathname) || url.pathname.split('/').includes('..')) return false;
  if (!['script', 'stylesheet', 'image', 'font'].includes(resourceType)) return false;
  return url.pathname.startsWith('/assets/') || url.pathname.startsWith('/_next/static/') ||
    (resourceType === 'image' && /^\/(?:brand\/)?[a-zA-Z0-9_-]+\.(?:png|jpg|jpeg|webp|svg|ico)$/.test(url.pathname));
}

export function validateSyntheticAccount(email) {
  assert.equal(email, 'synthetic-smoke@amaris.test', 'A dedicated synthetic production smoke account is required');
}
