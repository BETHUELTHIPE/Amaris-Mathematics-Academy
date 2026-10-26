import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file) => readFileSync(new URL(file, import.meta.url), "utf8");
const video = read("../components/site/video-request-form.tsx");
const videoApi = read("../app/api/video-requests/checkout/route.ts");
const contact = read("../components/site/enquiry-form.tsx");
const contactApi = read("../app/contact/actions.ts");
const registration = read("../app/register/page.tsx");
const tutorApplication = read("../components/tutor/application-form.tsx");
const tutorRegistration = read("../app/tutor/register/page.tsx");
const tutors = read("../components/tutor/slot-fields.tsx");
const curriculum = read("../components/site/curriculum-fields.tsx");
const location = read("../components/site/location-fields.tsx");

test("all mandatory video request inputs are browser-required", () => {
  for (const field of ["request_type", "preferred_duration_minutes", "explanation_style", "instructions", "documents"]) {
    assert.match(video, new RegExp('<(?:input|select|textarea) name="' + field + '"[^>]*\\brequired\\b'));
  }
  assert.match(video, /at least one supporting document/);
  assert.doesNotMatch(video, /Supporting documents \(optional\)/);
});
test("missing paid video form details never reach the payment checkout", () => {
  assert.match(videoApi, /Enter the required \$\{label\}/);
  assert.match(videoApi, /Attach at least one supporting document/);
  assert.match(videoApi, /status: 400/);
  assert.match(videoApi, /createStudentVideoRequestCheckout/);
});
test("required student registration, contact, tutor recruitment, booking selectors and slots remain enforced", () => {
  assert.match(registration, /name="terms" type="checkbox" required/);
  assert.match(registration, /name=\{name\} type=\{type\} required/);
  assert.match(contact, /name="fullName"[^>]*required/);
  assert.match(contact, /name="email"[^>]*required/);
  assert.match(contact, /name="phone"[^>]*required/);
  assert.match(contact, /name="message"[^>]*required/);
  assert.match(contactApi, /contactRequiredErrors/);
  assert.match(tutorRegistration, /name="consent" type="checkbox" required/);
  assert.match(tutorApplication, /name="documents" type="file"[^>]*required/);
  assert.match(tutorApplication, /programmes"\)\.length/);
  assert.match(tutors, /name="starts_at" type="datetime-local" required/);
  assert.match(tutors, /name="duration_hours" type="number" required/);
  assert.match(tutors, /name="zoom_join_url" type="url" required/);
  for (const field of ["programme", "subject", "level", "topic"]) {
    assert.match(curriculum, new RegExp('name="' + field + '"[^>]*\\brequired\\b'));
  }
  for (const field of ["country", "province", "city"]) {
    assert.match(location, new RegExp('name="' + field + '"[^>]*\\brequired\\b'));
  }
});
test("do not require hidden PayFast tokens, anti-spam honeypot, or opt-in publication switch", () => {
  assert.match(contact, /name="website" type="text"/);
  assert.doesNotMatch(tutors, /name="is_active"[^>]*required/);
});
