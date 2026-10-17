import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const file = readFileSync(new URL("../app/dashboard/orders/page.tsx", import.meta.url), "utf8");

test("dashboard gives verified orders a payment receipt PDF download", () => {
  assert.match(file, /Download payment receipt \(PDF\)/);
  assert.match(file, /verified paid invoice as a payment receipt/);
  assert.match(file, /if \(!order\.invoice_ready\) return null/);
  assert.match(file, /dashboard\/orders\/invoice\?reference=/);
  assert.match(file, /book-online-live-class\/invoice\?reference=/);
  assert.match(file, /request-a-video\/invoice\?reference=/);
  assert.match(file, /requireVerifiedStudent\("\/dashboard\/orders"\)/);
});
