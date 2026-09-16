import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const budgets = {
  maxJavaScriptChunk: 250 * 1024,
  maxStylesheet: 200 * 1024,
  maxHeroImage: 200 * 1024,
};

async function filesUnder(directory) {
  try {
    const entries = await readdir(directory, { withFileTypes: true });
    const nested = await Promise.all(
      entries.map(async (entry) => {
        const path = join(directory, entry.name);
        return entry.isDirectory() ? filesUnder(path) : [path];
      }),
    );
    return nested.flat();
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}

async function largest(paths, extension) {
  const matches = paths.filter((path) => path.endsWith(extension));
  const sized = await Promise.all(matches.map(async (path) => ({ path, size: (await stat(path)).size })));
  return sized.sort((left, right) => right.size - left.size)[0] ?? null;
}

const buildRoots = ["dist", ".vinext", ".next", ".output"];
const assets = (await Promise.all(buildRoots.map(filesUnder))).flat();
const largestJavaScript = await largest(assets, ".js");
const largestStylesheet = (await largest(assets, ".css")) ?? {
  path: "inlined/no-external-stylesheet",
  size: 0,
};

if (!largestJavaScript) {
  console.error(`FAIL no built JavaScript assets found under ${buildRoots.join(", ")}`);
  process.exit(1);
}

const checks = [
  ["largest JavaScript chunk", largestJavaScript, budgets.maxJavaScriptChunk],
  ["largest external stylesheet", largestStylesheet, budgets.maxStylesheet],
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
    console.log(`PASS ${result} (${asset.path})`);
  }
}

if (failed) process.exit(1);
