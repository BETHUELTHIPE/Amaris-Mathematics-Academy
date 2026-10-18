import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL("../" + path, import.meta.url), "utf8");
const button = read("components/site/share-website-button.tsx");
const enhancer = read("public/share-website-enhance.js");
const header = read("components/site/header.tsx");
const footer = read("components/site/footer.tsx");

test("public header and footer expose the share website control without React hydration", () => {
  assert.match(header, /<ShareWebsiteButton compact\s*\/>/);
  assert.match(footer, /<ShareWebsiteButton\s*\/>/);
  assert.match(footer, /Support Our Project/);
  assert.doesNotMatch(button, /"use client"|useState|useEffect|useRef/);
  assert.match(button, /data-share-trigger/);
  assert.match(button, /share-website-enhance\.js/);
  assert.match(enhancer, /__amarisShareInstalled/);
});

test("enhancement shares or copies ONLY the public homepage URL", () => {
  assert.match(enhancer, /navigator\.share\(\{ title: SHARE_TITLE, text: SHARE_MESSAGE, url \}\)/);
  assert.match(enhancer, /navigator\.clipboard\.writeText\(url\)/);
  assert.match(enhancer, /new URL\("\/", window\.location\.origin\)\.toString\(\)/);
  assert.doesNotMatch(enhancer, /location\.href|location\.search|location\.hash|localStorage|sessionStorage/);
});

test("native control retains keyboard, cancellation, manual copy, status and accessibility", () => {
  assert.match(button, /type="button"/);
  assert.match(button, /aria-label="Share website"/);
  assert.match(button, /role="status"/);
  assert.match(button, /aria-live="polite"/);
  assert.match(button, /readOnly/);
  assert.match(button, /focus-visible:/);
  assert.match(enhancer, /"AbortError"/);
  assert.match(enhancer, /input\.focus\(\)/);
  assert.match(enhancer, /input\.select\(\)/);
  assert.match(enhancer, /container\.hidden = false/);
  assert.match(enhancer, /button\.disabled = true/);
});
