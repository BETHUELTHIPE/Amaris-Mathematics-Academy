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
const filtersSource = fs.readFileSync(
  new URL("../app/book-online-live-class/live-class-booking-filters.tsx", import.meta.url),
  "utf8",
);
const slotsApiSource = fs.readFileSync(
  new URL("../lib/live-classes.ts", import.meta.url),
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

test("checkout preserves server-owned pricing and PayFast verification language", () => {
  assert.match(checkoutPage, /Pay R\{booking\.amount\} with PayFast/);
  assert.match(checkoutPage, /booking\.duration_minutes \/ 60/);
  assert.match(checkoutPage, /Server-priced/);
  assert.match(checkoutPage, /verified callback required/);
});

test("confirmation page releases Zoom only for confirmed bookings", () => {
  assert.match(confirmationPage, /booking\?\.status === "confirmed"/);
  assert.match(confirmationPage, /booking\.zoom_join_url/);
  assert.match(confirmationPage, /confirmation email and invoice/);
});

test("named tutor selection and 24-hour South African time filters are available", () => {
  assert.match(filtersSource, /name="tutor"/);
  assert.match(filtersSource, /Any available tutor/);
  assert.match(filtersSource, /name="time"/);
  assert.match(filtersSource, /overnight/);
  assert.match(bookingPage, /Africa\/Johannesburg/);
  assert.match(bookingPage, /selectedTutorId/);
  assert.match(bookingPage, /inPreferredTime/);
  assert.match(slotsApiSource, /tutor_id/);
});

test("booking page promises staff notifications only after payment verification", () => {
  assert.match(bookingPage, /Django admin team/);
  assert.match(bookingPage, /PayFast verifies payment/);
});
