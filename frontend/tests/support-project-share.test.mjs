import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL("../" + path, import.meta.url), "utf8");
const page = read("app/support-our-project/page.tsx");
const share = read("components/site/share-support-project.tsx");
const urls = read("lib/support-sharing.ts");

test("Support Our Project offers the public shareable URL and social preview", () => {
  assert.match(page, /<ShareSupportProject\s*\/>/);
  assert.match(page, /share-our-project/);
  assert.match(page, /alternates:\s*\{ canonical: PUBLIC_SUPPORT_URL \}/);
  assert.match(page, /openGraph:/);
  assert.match(urls, /https:\/\/amaris-mathematics-academy-live-students\.onrender\.com\/support-our-project/);
  assert.match(share, /value=\{PUBLIC_SUPPORT_URL\}/);
  assert.match(share, /readOnly/);
});

test("sharing uses official support-page link, not visitor query, payment or dashboard details", () => {
  assert.match(share, /navigator\.share\(\{/);
  assert.match(share, /url: PUBLIC_SUPPORT_URL/);
  assert.match(share, /navigator\.clipboard\.writeText\(PUBLIC_SUPPORT_URL\)/);
  assert.match(share, /href=\{SUPPORT_WHATSAPP_URL\}/);
  assert.match(urls, /encodeURIComponent\(SUPPORT_SHARE_MESSAGE \+ " " \+ PUBLIC_SUPPORT_URL\)/);
  assert.doesNotMatch(share, /window\.location|location\.search|sessionStorage|localStorage|PAYFAST_/);
});

test("share controls work with clipboard denial, cancellation, keyboard and screen readers", () => {
  assert.match(share, /type="button"/);
  assert.match(share, /role="status" aria-live="polite"/);
  assert.match(share, /error\.name === "AbortError"/);
  assert.match(share, /onFocus=\{\(event\) => event\.currentTarget\.select\(\)\}/);
  assert.match(share, /focus-visible:/);
  assert.match(share, /noopener noreferrer/);
  assert.match(share, /"manual"/);
});

test("support page retains contact, support, footer and existing payment-safety messaging", () => {
  assert.match(page, /href="\/contact"/);
  assert.match(page, /<Footer\s*\/>/);
  assert.match(page, /does not collect donations or card details/);
  assert.doesNotMatch(page, /PAYFAST_|MERCHANT_KEY|href="\/checkout/);
});
