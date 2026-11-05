import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { paginatePrivateRows } from "../lib/private-pagination.ts";

test("private dashboard pagination keeps every authorized item reachable", () => {
  const records = Array.from({ length: 101 }, (_, index) => ({ id: index + 1 }));
  const seen = [];
  for (let page = 1; page <= 9; page += 1) {
    const result = paginatePrivateRows(records, String(page), 12);
    assert.equal(result.count, 101);
    assert.equal(result.totalPages, 9);
    assert.equal(result.current, page);
    assert.ok(result.rows.length <= 12);
    seen.push(...result.rows.map(row => row.id));
  }
  assert.deepEqual(seen, records.map(row => row.id));
});

test("untrusted query numbers are bounded without creating huge arrays", () => {
  const records = ["a", "b", "c"];
  for (const invalid of ["-1", "0", "1.5", "NaN", "Infinity", "1e5", "+1", " 1", "12345678", ""]) {
    assert.deepEqual(paginatePrivateRows(records, invalid, 2).rows, ["a", "b"], invalid);
  }
  assert.deepEqual(paginatePrivateRows(records, "999999", 2).rows, ["c"]);
  assert.deepEqual(paginatePrivateRows([], "999999", 12), { rows: [], current: 1, totalPages: 1, count: 0 });
  assert.throws(() => paginatePrivateRows(records, undefined, 0), RangeError);
  assert.throws(() => paginatePrivateRows(records, undefined, 101), RangeError);
});

test("private pages authenticate and bound rendered lists with server-only links", async () => {
  const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const overview = await read("../app/dashboard/page.tsx");
  const orders = await read("../app/dashboard/orders/page.tsx");
  const notifications = await read("../app/dashboard/notifications/page.tsx");
  const tutor = await read("../app/tutor/dashboard/page.tsx");
  const api = await read("../lib/student-api.ts");
  const tutorApi = await read("../lib/tutor-api.ts");
  for (const page of [overview, orders, notifications, tutor]) {
    assert.match(page, /paginatePrivateRows\(/);
    assert.match(page, /<PrivatePagination /);
    assert.doesNotMatch(page, /force-static|unstable_cache/);
  }
  assert.match(overview, /requireVerifiedStudent\("\/dashboard"\)/);
  assert.match(orders, /requireVerifiedStudent\("\/dashboard\/orders"\)/);
  assert.match(notifications, /requireVerifiedStudent\("\/dashboard\/notifications"\)/);
  assert.match(tutor, /dashboard = await getTutorDashboard\(\)/);
  assert.match(tutor, /getTutorEarnings\(\)/);
  assert.match(api, /cache: "no-store"/);
  assert.match(tutorApi, /cache: "no-store"/);
  assert.match(tutor, /createTutorSlotAction|updateTutorSlotAction|pauseTutorSlotAction/);
  assert.match(orders, /invoiceLink\(order\)/);
  assert.match(notifications, /notification\.href/);
  assert.match(tutor, /formatSessionTime\(slot\.starts_at\)/);
});
