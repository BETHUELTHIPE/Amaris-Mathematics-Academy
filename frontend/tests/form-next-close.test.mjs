import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (relative) => fs.readFileSync(path.join(process.cwd(), relative), "utf8");

const formPages = [
  ["app/register/page.tsx", "Create student profile"],
  ["app/login/page.tsx", "Log in securely"],
  ["app/forgot-password/page.tsx", "Send reset link"],
  ["app/reset-password/page.tsx", "Update password"],
  ["app/verify-email/page.tsx", "Verify email"],
  ["app/book-online-live-class/live-class-booking-filters.tsx", "Show available tutor times"],
  ["app/checkout/[slug]/page.tsx", "Continue to PayFast"],
  ["app/book-online-live-class/checkout/page.tsx", "Pay R250 with PayFast"],
  ["app/learn/[courseSlug]/[lessonSlug]/page.tsx", "Save progress"],
];

for (const [file, action] of formPages) {
  test(`${file} shows Next and a safe Close while preserving the existing submit`, () => {
    const source = read(file);
    assert.match(source, /<form\b/);
    assert.ok(source.includes(`Next: ${action}`), "Next must describe the real next action");
    assert.match(source, /<button\s+type="submit"/);
    assert.match(source, /<FormCloseLink\s+href=/);
  });
}

test("Close is accessible navigation, never an accidental form submission", () => {
  const source = read("components/site/form-close-link.tsx");
  assert.match(source, /import Link from "next\/link"/);
  assert.match(source, /aria-label="Close form without submitting"/);
  assert.match(source, /focus-visible:outline/);
  assert.match(source, /<Link\s/);
  assert.doesNotMatch(source, /<button|type="submit"|onClick/);
});

test("contact enquiry retains validation, action state, and confirmation while offering both buttons", () => {
  const source = read("components/site/enquiry-form.tsx");
  assert.match(source, /action=\{formAction\}/);
  assert.match(source, /Next: Send enquiry/);
  assert.match(source, /<SubmitButton\s*\/>(\s*)<FormCloseLink href="\/"\s*\/>/);
  assert.match(source, /state.status === "success"/);
  assert.match(source, /<FormCloseLink href="\/contact"\s*\/>/);
  assert.match(source, /required maxLength=\{80\}/);
});

test("video request keeps server-priced checkout and separate non-submitting exits", () => {
  const source = read("components/site/video-request-form.tsx");
  assert.match(source, /onSubmit=\{submit\}/);
  assert.match(source, /Next: Review secure payment/);
  assert.match(source, /Next: Continue to PayFast/);
  assert.equal((source.match(/<FormCloseLink href="\/dashboard"\s*\/>/g) || []).length, 2);
  assert.match(source, /checkout.gateway_url/);
  assert.match(source, /name="documents" type="file"/);
  assert.doesNotMatch(source, /window.location.assign\(.*payfast/);
});

test("booking and course payments remain POST forms using signed provider fields", () => {
  for (const file of ["app/checkout/[slug]/page.tsx", "app/book-online-live-class/checkout/page.tsx"]) {
    const source = read(file);
    assert.match(source, /<form method="post" action=\{checkout.gateway_url\}/);
    assert.match(source, /Object.entries\(checkout.fields\)/);
    assert.match(source, /<FormCloseLink/);
  }
});

test("verify email preserves both verification and resend endpoints", () => {
  const source = read("app/verify-email/page.tsx");
  assert.match(source, /action=\{verifyEmailAction\}/);
  assert.match(source, /action=\{resendVerificationAction\}/);
  assert.match(source, /Next: Send a new code/);
  assert.match(source, /<FormCloseLink href="\/login"/);
});

test("Amaris Assistant Next submits a question; Close dismisses without a request", () => {
  const source = read("components/site/amaris-assistant.tsx");
  assert.match(source, /<form onSubmit=\{onSubmit\}/);
  assert.match(source, /aria-label="Next: send question"/);
  assert.match(source, /type="button" onClick=\{\(\) => setOpen\(false\)\}/);
  assert.match(source, />Close<\/button>/);
});
