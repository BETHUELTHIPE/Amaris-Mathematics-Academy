import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const footerSource = await readFile(
  new URL("../components/site/footer.tsx", import.meta.url),
  "utf8",
);
const adminPageSource = await readFile(
  new URL("../app/amaris-admin/page.tsx", import.meta.url),
  "utf8",
);
const djangoUrlsSource = await readFile(
  new URL("../../backend/amaris_cms/urls.py", import.meta.url),
  "utf8",
);

test("Amaris Admin is discoverable from the public footer", () => {
  assert.match(footerSource, /href="\/amaris-admin"/);
  assert.match(footerSource, />Amaris Admin<\/a>/);
});

test("Amaris Admin links to the deployed Django admin login, not a duplicate login form", () => {
  assert.match(adminPageSource, /https:\/\/amaris-production-web\.onrender\.com\/admin\//);
  assert.match(adminPageSource, /href=\{DJANGO_ADMIN_URL\}/);
  assert.match(djangoUrlsSource, /path\("admin\/", admin\.site\.urls\)/);
  assert.doesNotMatch(adminPageSource, /<form\b|<input\b/i);
});

test("admin gateway clearly restricts access and avoids search indexing", () => {
  assert.match(adminPageSource, /authorized Amaris staff/);
  assert.match(adminPageSource, /robots: \{ index: false, follow: false \}/);
  assert.match(adminPageSource, /target="_blank"/);
  assert.match(adminPageSource, /rel="noopener noreferrer"/);
  assert.match(adminPageSource, /focus-visible:outline/);
  assert.match(adminPageSource, /aria-label="Open Django administration/);
});
