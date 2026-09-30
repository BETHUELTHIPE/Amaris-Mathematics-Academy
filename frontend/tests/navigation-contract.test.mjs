import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const cmsSource = await readFile(new URL("../lib/cms.ts", import.meta.url), "utf8");
const headerSource = await readFile(
  new URL("../components/site/header.tsx", import.meta.url),
  "utf8",
);
const authControlsSource = await readFile(
  new URL("../components/site/auth-controls.tsx", import.meta.url),
  "utf8",
);

const requiredLinks = [
  ["/courses", "Courses"],
  ["/how-it-works", "How it works"],
  ["/book-online-live-class", "Book online live class"],
  ["/pricing", "Pricing"],
  ["/about", "About"],
  ["/contact", "Contact"],
];

test("keeps all core public pages in managed navigation", () => {
  for (const [url, label] of requiredLinks) {
    assert.ok(cmsSource.includes(`label: "${label}"`), `missing ${label} label`);
    assert.ok(cmsSource.includes(`url: "${url}"`), `missing ${url} URL`);
  }
  assert.match(cmsSource, /location: "both" as const/);
  assert.match(cmsSource, /return \[\.\.\.requiredItems, \.\.\.customItems\]/);
});

test("renders managed links in desktop and mobile header navigation", () => {
  assert.match(headerSource, /getManagedNavigation\("header"\)/);
  assert.match(headerSource, /links\.map/);
  assert.match(authControlsSource, /links\.map/);
});
