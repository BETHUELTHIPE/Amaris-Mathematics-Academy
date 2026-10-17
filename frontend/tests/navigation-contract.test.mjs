import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const cmsSource = await readFile(new URL("../lib/cms.ts", import.meta.url), "utf8");
const headerSource = await readFile(
  new URL("../components/site/header.tsx", import.meta.url),
  "utf8",
);
const footerSource = await readFile(
  new URL("../components/site/footer.tsx", import.meta.url),
  "utf8",
);
const djangoUrlsSource = await readFile(
  new URL("../../backend/amaris_cms/urls.py", import.meta.url),
  "utf8",
);
const authControlsSource = await readFile(
  new URL("../components/site/auth-controls.tsx", import.meta.url),
  "utf8",
);

const requiredLinks = [
  ["/courses", "Courses"],
  ["/how-it-works", "How it works"],
  ["/pricing", "Pricing"],
  ["/about", "About"],
  ["/book-online-live-class", "Book online live class"],
  ["/contact", "Contact"],
];

test("keeps all core public pages in managed navigation", () => {
  for (const [url, label] of requiredLinks) {
    assert.ok(cmsSource.includes(`label: "${label}"`), `missing ${label} label`);
    assert.ok(cmsSource.includes(`url: "${url}"`), `missing ${url} URL`);
  }
  assert.match(cmsSource, /location: "both" as const/);
  assert.match(cmsSource, /order: requiredItem\.order/);
  assert.match(cmsSource, /return \[\.\.\.requiredItems, \.\.\.customItems\]/);
});

test("keeps Book online live class immediately next to Contact", () => {
  assert.match(
    cmsSource,
    /label: "Book online live class"[\s\S]*order: 45[\s\S]*label: "Contact"[\s\S]*order: 50/,
  );
  assert.match(cmsSource, /function keepBookingNextToContact/);
  assert.match(cmsSource, /return keepBookingNextToContact\(items\)/);
});

test("renders managed links in desktop and mobile header navigation", () => {
  assert.match(headerSource, /getManagedNavigation\("header"\)/);
  assert.match(headerSource, /links\.map/);
  assert.match(authControlsSource, /links\.map/);
});

test("Django Admin appears in the shared footer with a safe backend link", () => {
  assert.match(footerSource, /getDjangoAdminUrl\(\)/);
  assert.match(footerSource, /process\.env\.DJANGO_ADMIN_URL/);
  assert.match(footerSource, /process\.env\.CMS_API_URL/);
  assert.match(footerSource, /new URL\("\/admin\/", origin\)\.toString\(\)/);
  assert.match(footerSource, /href=\{djangoAdminUrl\} target="_blank" rel="noopener noreferrer"/);
  assert.match(footerSource, /Django Admin<\/a>/);
  assert.match(djangoUrlsSource, /path\("admin\/", admin\.site\.urls\)/);
});
