import assert from "node:assert/strict";
import test from "node:test";
import { groupDevice, groupPage, validVital } from "../lib/web-vitals.ts";

test("routes are classified without emitting student, payment, or URL identifiers", () => {
  assert.equal(groupPage("/"), "home");
  assert.equal(groupPage("/courses"), "courses");
  assert.equal(groupPage("/courses/private-module-120"), "course-detail");
  assert.equal(groupPage("/student/orders/reference-123"), "student");
  assert.equal(groupPage("/payment/reference-secret"), "student");
  assert.equal(groupPage("/tutor/dashboard"), "tutor");
  assert.equal(groupPage("/book-online-live-class"), "booking");
  assert.equal(groupPage("/unknown"), "other");
  assert.equal(groupPage("/announcements"), "announcements");
});

test("device dimensions are coarse and never fingerprint the device", () => {
  assert.equal(groupDevice(320), "mobile");
  assert.equal(groupDevice(600), "mobile");
  assert.equal(groupDevice(768), "tablet");
  assert.equal(groupDevice(1024), "tablet");
  assert.equal(groupDevice(1440), "desktop");
});

test("strict sample shape rejects arbitrary URL, identity, scripts, and invalid timings", () => {
  const sample = { name: "INP", value: 175, id: "v4-metric-example", page: "courses", device: "mobile" };
  assert.equal(validVital(sample), true);
  for (const bad of [
    { ...sample, name: "FID" },
    { ...sample, page: "/student/302?a=token" },
    { ...sample, device: "Chrome on Android 18" },
    { ...sample, id: "1" },
    { ...sample, value: NaN },
    { ...sample, value: Infinity },
    { ...sample, value: -1 },
    { ...sample, value: 80000 },
    { ...sample, email: "person@example.test" },
    { ...sample, url: "https://example.test/user?id=4" },
  ]) assert.equal(validVital(bad), false);
  assert.equal(validVital({ ...sample, name: "CLS", value: 0.17 }), true);
});
