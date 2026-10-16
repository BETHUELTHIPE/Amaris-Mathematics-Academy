import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const readFrontend = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("Support Our Project is reachable from the public footer", () => {
  const footer = readFrontend("components/site/footer.tsx");
  assert.match(footer, /href="\/support-our-project"/);
  assert.match(footer, /Support Our Project/);
});

test("support page uses the public website layout and contact routes", () => {
  const page = readFrontend("app/support-our-project/page.tsx");
  assert.match(page, /title: "Support Our Project"/);
  assert.match(page, /<Header\s*\/>/);
  assert.match(page, /<Footer\s*\/>/);
  assert.match(page, /href="\/contact"/);
  assert.match(page, /href=\{academyBrand\.emailHref\}/);
});

test("support page contains a secure checkout guarded by provider availability", () => {
  const page = readFrontend("app/support-our-project/page.tsx");
  const form = readFrontend("components/site/donation-checkout-form.tsx");
  assert.match(page, /DonationCheckoutForm/);
  assert.match(form, /availability==="disabled"/);
  assert.match(page, /never collects card details/);
  assert.doesNotMatch(page, /PAYFAST_|MERCHANT_KEY|bank account number/i);
});
