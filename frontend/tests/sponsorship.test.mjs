import assert from "node:assert/strict";
import test from "node:test";
import { getSponsorshipPaymentUrl } from "../lib/sponsorship.ts";

test("sponsorship only links to a live HTTPS PayFast payment destination", () => {
  for (const url of ["https://www.payfast.co.za/donate/go/merchant", "https://payment.payfast.io/eng/process/payment-id"]) {
    assert.equal(getSponsorshipPaymentUrl(url), url);
  }
  for (const url of ["", "not a url", "http://www.payfast.co.za/donate/go/merchant", "https://payfast.co.za.evil.test/pay", "https://sandbox.payfast.co.za/pay", "https://user:secret@www.payfast.co.za/pay", "https://www.payfast.co.za:8443/pay", "https://www.payfast.co.za/"]) {
    assert.equal(getSponsorshipPaymentUrl(url), null, url);
  }
});

test("sandbox amounts are bounded and mode defaults to testing", async () => {
  const { sponsorshipAmount, sponsorshipMode } = await import("../lib/sponsorship.ts");
  assert.equal(sponsorshipMode(), "sandbox");
  assert.equal(sponsorshipMode("live"), "live");
  assert.equal(sponsorshipAmount("100.5"), "100.50");
  assert.equal(sponsorshipAmount("5"), "5.00");
  assert.equal(sponsorshipAmount("100000"), "100000.00");
  for (const amount of [undefined, "-1", "0", "4.99", "100000.01", "1e3", "100.001", "NaN", ["100"]]) assert.equal(sponsorshipAmount(amount), null);
});
