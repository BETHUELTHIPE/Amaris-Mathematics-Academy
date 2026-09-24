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

test("checkout preserves server-owned pricing and PayFast verification language", () => {
  assert.match(checkoutPage, /Pay R250 with PayFast/);
  assert.match(checkoutPage, /Server-priced/);
  assert.match(checkoutPage, /verified callback required/);
});

test("confirmation page releases Zoom only for confirmed bookings", () => {
  assert.match(confirmationPage, /booking\?\.status === "confirmed"/);
  assert.match(confirmationPage, /booking\.zoom_join_url/);
  assert.match(confirmationPage, /confirmation email and invoice/);
});
