import assert from "node:assert/strict";
import test from "node:test";
import { websiteFallback } from "../lib/assistant-fallback.ts";

test("offers published paths when AI is unavailable", () => {
  assert.match(websiteFallback("What mathematics pathways are available?"), /CAPS, IEB, TVET and university/);
  assert.match(websiteFallback("How do I create a profile?"), /\/register/);
  assert.match(websiteFallback("I forgot my password"), /\/forgot-password/);
  assert.match(websiteFallback("What does this course cost?"), /\/pricing/);
});

test("does not invent prices, private payment status or answers to unknown questions", () => {
  assert.doesNotMatch(websiteFallback("What does this course cost?"), /R\s?\d/);
  assert.match(websiteFallback("Is my invoice paid?"), /cannot see individual payment or invoice status/);
  assert.match(websiteFallback("Will you guarantee my grade?"), /cannot verify an answer/);
});
