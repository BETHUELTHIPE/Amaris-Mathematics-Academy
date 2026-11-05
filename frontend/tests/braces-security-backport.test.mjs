import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const braces = require("braces");
const bracesPackage = require("braces/package.json");

test("uses the Amaris patched braces backport", () => {
  assert.equal(bracesPackage.version, "3.0.4-amaris.0");
  assert.deepEqual(braces.expand("{a,b}"), ["a", "b"]);
});

test("rejects deeply nested brace patterns before stack exhaustion", () => {
  const nested = "{".repeat(101) + "a,b" + "}".repeat(101);
  assert.throws(() => braces(nested), /exceeds max depth/);
});
