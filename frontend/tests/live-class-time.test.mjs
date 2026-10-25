import assert from "node:assert/strict";
import test from "node:test";
import { inPreferredTime } from "../lib/live-class-time.mjs";

test("SAST booking windows cover every hour exactly once, including overnight", () => {
  const windows = ["morning", "afternoon", "evening", "overnight"];
  for (let hour = 0; hour < 24; hour++) {
    const start = `2027-02-01T${String(hour).padStart(2, "0")}:30:00+02:00`;
    assert.equal(windows.filter((window) => inPreferredTime(start, window)).length, 1);
    assert.equal(inPreferredTime(start, "any"), true);
  }
});

test("UTC boundaries are classified using South African time", () => {
  const cases = [
    ["02:59:59", "overnight"], ["03:00:00", "morning"],
    ["09:59:59", "morning"], ["10:00:00", "afternoon"],
    ["14:59:59", "afternoon"], ["15:00:00", "evening"],
    ["19:59:59", "evening"], ["20:00:00", "overnight"],
    ["22:00:00", "overnight"],
  ];
  for (const [time, window] of cases) {
    assert.equal(inPreferredTime(`2027-02-01T${time}Z`, window), true, time);
  }
  assert.equal(inPreferredTime("invalid", "any"), false);
  assert.equal(inPreferredTime("invalid", "overnight"), false);
});
