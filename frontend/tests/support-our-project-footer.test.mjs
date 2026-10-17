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

test("support page does not imply a live donation checkout", () => {
  const page = readFrontend("app/support-our-project/page.tsx");
  assert.match(page, /does not collect donations or card details/);
  assert.doesNotMatch(page, /href="\/checkout/);
  assert.doesNotMatch(page, /PAYFAST_|MERCHANT_KEY|bank account number/i);
});

test("support page has its own investor enquiry form, distinct from student contact", () => {
  const page = readFrontend("app/support-our-project/page.tsx");
  const form = readFrontend("app/support-our-project/partnership-enquiry-form.tsx");
  assert.match(page, /<PartnershipEnquiryForm\s*\/>/);
  assert.match(page, /potential investors, donors, sponsors/);
  assert.match(form, /Investor and partnership enquiry/);
  assert.match(form, /Investment \/ funding proposal/);
  assert.match(form, /Company \/ organisation/);
  assert.match(form, /name="consent"/);
  assert.match(form, /aria-live="polite"/);
});

test("investor enquiries are distinctly categorised and validated server-side", () => {
  const action = readFrontend("app/support-our-project/actions.ts");
  assert.match(action, /partnershipSchema\.safeParse/);
  assert.match(action, /Project support/);
  assert.match(action, /NOT A STUDENT SUPPORT REQUEST/);
  assert.match(action, /project-partnership/);
  assert.match(action, /consent: z\.literal\("on"/);
  assert.match(action, /website: z\.string\(\)\.max\(0\)/);
  assert.doesNotMatch(action, /PAYFAST_MERCHANT|OPENAI_API_KEY|supabase_service_role/i);
});
