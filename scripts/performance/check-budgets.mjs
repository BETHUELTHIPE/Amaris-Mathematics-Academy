import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const budgets = {
  maxJavaScriptChunk: 250 * 1024,
  maxStylesheet: 200 * 1024,
  maxHeroImage: 200 * 1024,
};

async function filesUnder(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? filesUnder(path) : [path];
    }),
  );
  return nested.flat();
}

async function largest(paths, extension) {
  const matches = paths.filter((path) => path.endsWith(extension));
  const sized = await Promise.all(matches.map(async (path) => ({ path, size: (await stat(path)).size })));
  return sized.sort((left, right) => right.size - left.size)[0] ?? { path: extension, size: 0 };
}

const assets = await filesUnder("dist/client/assets");
const checks = [
  ["largest JavaScript chunk", await largest(assets, ".js"), budgets.maxJavaScriptChunk],
  ["largest stylesheet", await largest(assets, ".css"), budgets.maxStylesheet],
  [
    "homepage hero image",
    { path: "public/amaris-math-hero.webp", size: (await stat("public/amaris-math-hero.webp")).size },
    budgets.maxHeroImage,
  ],
];

let failed = false;
for (const [label, asset, limit] of checks) {
  const result = `${label}: ${(asset.size / 1024).toFixed(1)} KiB / ${(limit / 1024).toFixed(0)} KiB`;
  if (asset.size > limit) {
    failed = true;
    console.error(`FAIL ${result} (${asset.path})`);
  } else {
    console.log(`PASS ${result}`);
  }
}

if (failed) process.exit(1);

