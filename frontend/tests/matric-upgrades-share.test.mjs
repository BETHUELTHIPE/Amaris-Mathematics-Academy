import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL("../" + path, import.meta.url), "utf8");
const page = read("app/matric-upgrades/page.tsx");
const share = read("components/site/share-matric-upgrades.tsx");
const urls = read("lib/matric-upgrades-sharing.ts");

test("Matric Upgrades shows a prominent shareable link and canonical Open Graph URL", () => {
  assert.match(page, /<ShareMatricUpgrades\s*\/>/);
  assert.match(page, /share-matric-upgrades/);
  assert.match(page, /alternates:\s*\{ canonical: PUBLIC_MATRIC_UPGRADES_URL \}/);
  assert.match(page, /openGraph:/);
  assert.match(urls, /https:\/\/amaris-mathematics-academy-live-students\.onrender\.com\/matric-upgrades/);
  assert.match(share, /value=\{PUBLIC_MATRIC_UPGRADES_URL\}/);
  assert.match(share, /readOnly/);
});

test("copy, native sharing and WhatsApp use the public route, never session details", () => {
  assert.match(share, /navigator\.share\(\{/);
  assert.match(share, /url: PUBLIC_MATRIC_UPGRADES_URL/);
  assert.match(share, /navigator\.clipboard\.writeText\(PUBLIC_MATRIC_UPGRADES_URL\)/);
  assert.match(share, /href=\{MATRIC_UPGRADES_WHATSAPP_URL\}/);
  assert.match(urls, /encodeURIComponent\(MATRIC_UPGRADES_SHARE_MESSAGE \+ " " \+ PUBLIC_MATRIC_UPGRADES_URL\)/);
  assert.doesNotMatch(share, /location\.href|location\.search|location\.hash|localStorage|sessionStorage|PAYFAST_/);
});

test("sharing has accessible controls and a clipboard fallback", () => {
  assert.match(share, /type="button"/);
  assert.match(share, /role="status" aria-live="polite"/);
  assert.match(share, /error\.name === "AbortError"/);
  assert.match(share, /status === "manual"/);
  assert.match(share, /useEffect\(\(\) => \{/);
  assert.match(share, /urlInput\.current\?\.select\(\)/);
  assert.match(share, /focus-visible:/);
  assert.match(share, /noopener noreferrer/);
});

test("matric registration and tuition safeguards remain unchanged", () => {
  assert.match(page, /secure your exam centre before attending Amaris classes/i);
  assert.match(page, /href="\/register"/);
  assert.match(page, /href="\/book-online-live-class"/);
  assert.match(page, /href="\/contact"/);
  assert.match(page, /<Footer\s*\/>/);
  assert.doesNotMatch(page, /PAYFAST_|MERCHANT_KEY|href="\/checkout/);
});
