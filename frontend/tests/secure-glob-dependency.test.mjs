import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);

// This replacement is deliberately scoped to an upstream-unpatched dev-only
// glob-matching dependency. The ordinary lint/build/E2E gates must also pass.
test("micromatch replacement uses bounded picomatch and safe brace expansion", () => {
  const manifest = require("micromatch/package.json");
  assert.equal(manifest.name, "micromatch-safe-amaris");
  assert.equal(manifest.version, "4.0.8-amaris.1");
  assert.equal(manifest.dependencies?.picomatch, "4.0.7");
  assert.equal(manifest.dependencies?.["@isaacs/brace-expansion"], "5.0.1");
  const matcher = require("micromatch");
  assert.equal(matcher.isMatch("components/button.tsx", "**/*.{ts,tsx}"), true);
  assert.equal(matcher.isMatch("components/button.css", "**/*.{ts,tsx}"), false);
  assert.equal(matcher.isMatch(".hidden/config.js", "**/*.js", { dot: true }), true);
  assert.equal(matcher.scan("src/**/*.{ts,tsx}").isGlob, true);
  assert.deepEqual(matcher.braces("src/*.{ts,tsx}", { expand: true }), ["src/*.ts", "src/*.tsx"]);
  assert.throws(() => matcher.braces("{".repeat(80) + "x" + "}".repeat(80), { expand: true }), RangeError);
});

test("both fast-glob dependency paths retain brace and negative pattern matching", () => {
  const root = mkdtempSync(join(tmpdir(), "amaris-safe-glob-"));
  try {
    mkdirSync(join(root, "src", "ui"), { recursive: true });
    writeFileSync(join(root, "src", "app.ts"), "export {};");
    writeFileSync(join(root, "src", "ui", "button.tsx"), "export {};");
    writeFileSync(join(root, "src", "ignore.ts"), "export {};");
    writeFileSync(join(root, "src", "ui", "style.css"), "");
    const expected = ["src/app.ts", "src/ui/button.tsx"];
    const base = require("fast-glob");
    assert.deepEqual(
      base.sync(["src/**/*.{ts,tsx}", "!src/**/ignore.ts"], { cwd: root }).sort(),
      expected,
    );
    const nestedRequire = createRequire(join(process.cwd(), "node_modules", "vite-plugin-dynamic-import", "package.json"));
    const nested = nestedRequire("fast-glob");
    assert.deepEqual(
      nested.sync(["src/**/*.{ts,tsx}", "!src/**/ignore.ts"], { cwd: root }).sort(),
      expected,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
