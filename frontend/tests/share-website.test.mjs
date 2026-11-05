import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL("../" + path, import.meta.url), "utf8");
const button = read("components/site/share-website-button.tsx");
const header = read("components/site/header.tsx");
const footer = read("components/site/footer.tsx");

test("public header and footer both expose the share website button", () => {
  assert.match(header, /<ShareWebsiteButton compact\s*\/>/);
  assert.match(footer, /<ShareWebsiteButton\s*\/>/);
  assert.match(footer, /Support Our Project/);
});

test("mobile uses native Web Share and desktop copies a public homepage link", () => {
  assert.match(button, /navigator\.share\(\{ title: SHARE_TITLE, text: SHARE_MESSAGE, url \}\)/);
  assert.match(button, /navigator\.clipboard\.writeText\(url\)/);
  assert.match(button, /new URL\("\/", window\.location\.origin\)\.toString\(\)/);
  assert.doesNotMatch(button, /location\.href|location\.search|location\.hash|localStorage|sessionStorage/);
});

test("sharing respects cancellation, keyboard interaction, copy errors and accessibility", () => {
  assert.match(button, /type="button"/);
  assert.match(button, /aria-label=\{label\}/);
  assert.match(button, /role="status"/);
  assert.match(button, /aria-live="polite"/);
  assert.match(button, /error\.name === "AbortError"/);
  assert.match(button, /status === "manual"/);
  assert.match(button, /readOnly/);
  assert.match(button, /onFocus=\{\(event\) => event\.currentTarget\.select\(\)\}/);
  assert.match(button, /focus-visible:/);
});
