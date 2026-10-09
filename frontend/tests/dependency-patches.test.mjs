import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
const lock = JSON.parse(readFileSync(resolve(root, "package-lock.json"), "utf8"));

test("patched image processing and source-map packages stay pinned", () => {
  for (const [name, version] of Object.entries({
    sharp: "0.35.5",
    "source-map-js": "1.2.2",
  })) {
    assert.equal(manifest.overrides?.[name], version, `Missing secure override for ${name}`);

    const found = Object.entries(lock.packages ?? {}).filter(
      ([path]) => path === `node_modules/${name}` || path.endsWith(`/node_modules/${name}`),
    );

    assert.ok(found.length > 0, `Missing installed package: ${name}`);
    for (const [path, pkg] of found) {
      assert.equal(pkg.version, version, `Unexpected ${name} version at ${path}`);
    }
  }
});

test("Cloudflare Vite tooling lockfile stays synchronized with its patched manifest", () => {
  const expected = "1.63.1";
  assert.equal(manifest.devDependencies["@cloudflare/vite-plugin"], expected);
  assert.equal(lock.packages?.[""].devDependencies?.["@cloudflare/vite-plugin"], expected);
  assert.equal(lock.packages?.["node_modules/@cloudflare/vite-plugin"]?.version, expected);
});
