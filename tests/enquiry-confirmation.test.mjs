import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = readFileSync(
  new URL("../components/site/enquiry-form.tsx", import.meta.url),
  "utf8",
);
const success = source.split('if (state.status === "success") {')[1]?.split("\n  return (")[0];

test("successful contact enquiry shows a close control that returns to a fresh contact form", () => {
  assert.ok(success, "successful enquiry confirmation must exist");
  assert.match(success, /Enquiry received/);
  assert.match(success, /<button type="button"[^>]*aria-label="Close enquiry confirmation and return to contact form"/);
  assert.match(success, /onClick=\{\(\) => window\.location\.assign\("\/contact"\)\}/);
  assert.match(success, />Close<\/button>/);
  assert.match(source, /useActionState\(submitEnquiry, initialEnquiryState\)/);
});

test("the enquiry confirmation places keyboard and screen-reader focus on its heading", () => {
  assert.match(source, /useEffect\(\(\) => \{\s*if \(state\.status === "success"\) confirmationHeadingRef\.current\?\.focus\(\);\s*\}, \[state\.status\]\)/);
  assert.match(success, /<h3 ref=\{confirmationHeadingRef\} tabIndex=\{-1\}/);
  assert.match(success, /focus-visible:outline-2/);
});
