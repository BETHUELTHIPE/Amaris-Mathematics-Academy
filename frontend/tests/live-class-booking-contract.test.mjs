import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const bookingPage = fs.readFileSync(
  new URL("../app/book-online-live-class/page.tsx", import.meta.url),
  "utf8",
);
const checkoutPage = fs.readFileSync(
  new URL("../app/book-online-live-class/checkout/page.tsx", import.meta.url),
  "utf8",
);
const confirmationPage = fs.readFileSync(
  new URL("../app/book-online-live-class/confirmation/page.tsx", import.meta.url),
  "utf8",
);
const cmsSource = fs.readFileSync(
  new URL("../lib/cms.ts", import.meta.url),
  "utf8",
);

test("live class booking is surfaced in managed navigation", () => {
  assert.match(cmsSource, /Book online live class/);
  assert.match(cmsSource, /\/book-online-live-class/);
});

test("booking page exposes the required programme and subject choices", () => {
  for (const label of ["CAPS", "IEB", "TVET", "University"]) {
    assert.match(bookingPage, new RegExp(label));
  }
  assert.match(bookingPage, /Mathematics/);
  assert.match(bookingPage, /Mathematical Literacy/);
  assert.match(bookingPage, /R250/);
  assert.match(bookingPage, /30-minute reminder/);
});

test("main booking route is private and requires the authoritative verified email before timetable lookups", () => {
  assert.match(bookingPage, /import \{ requireVerifiedStudent \} from "@\/lib\/auth"/);
  const gate = bookingPage.indexOf("await requireVerifiedStudent(");
  const timetable = bookingPage.indexOf("await getLiveClassSlots(");
  assert.ok(gate > -1 && timetable > gate, "verify email before fetching any private tutor availability");
  assert.match(bookingPage, /new URLSearchParams\(\)/);
  assert.match(bookingPage, /"programme", "subject", "level", "customLevel", "topic", "customTopic"/);
  assert.match(bookingPage, /robots: \{ index: false, follow: false \}/);
});

test("checkout, confirmation and invoice require a verified student identity", () => {
  const invoice = fs.readFileSync(
    new URL("../app/book-online-live-class/invoice/route.ts", import.meta.url), "utf8",
  );
  for (const protectedSource of [checkoutPage, confirmationPage, invoice]) {
    assert.match(protectedSource, /await requireVerifiedStudent\(/);
  }
});

test("checkout preserves server-owned pricing and PayFast verification language", () => {
  assert.match(checkoutPage, /Pay R\\$\\{booking\\.amount\\} with PayFast/);
  assert.match(checkoutPage, /PayFastHostedCheckout/);
  assert.match(checkoutPage, /booking\.duration_minutes \/ 60/);
  assert.match(checkoutPage, /Server-priced/);
  assert.match(checkoutPage, /verified callback required/);
});

test("confirmation page releases Zoom only for confirmed bookings", () => {
  assert.match(confirmationPage, /booking\?\.status === "confirmed"/);
  assert.match(confirmationPage, /booking\.zoom_join_url/);
  assert.match(confirmationPage, /confirmation email and invoice/);
});
