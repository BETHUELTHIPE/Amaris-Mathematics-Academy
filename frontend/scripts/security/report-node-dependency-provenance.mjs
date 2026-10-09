#!/usr/bin/env node
/**
 * Lockfile provenance for unresolved npm advisories. This is diagnostic only:
 * the full npm audit HIGH/CRITICAL release gate must still run and pass.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const lock = JSON.parse(readFileSync(resolve(here, "../../package-lock.json"), "utf8"));
const packages = lock.packages ?? {};
const requiredPatches = new Map([
  ["sharp", "0.35.5"],
  ["source-map-js", "1.2.2"],
]);

let violations = 0;
for (const [name, minimum] of requiredPatches) {
  const item = packages[`node_modules/${name}`];
  if (!item || item.version !== minimum) {
    console.error(`Dependency remediation is not locked: ${name} must be ${minimum}, found ${item?.version ?? "missing"}`);
    violations++;
  } else {
    console.log(`Verified locked remediation: ${name}@${minimum}`);
  }
}

const issue = packages["node_modules/braces"];
if (issue) {
  const parents = Object.entries(packages)
    .filter(([, pkg]) => pkg.dependencies?.braces || pkg.optionalDependencies?.braces)
    .map(([path, pkg]) => ({ path, dev: pkg.dev === true }));
  console.log("Unpatched braces advisory GHSA-vfj7-8cjw-p6xm remains present.");
  console.log(`Resolved braces version: ${issue.version}; lockfile development-only: ${issue.dev === true}`);
  for (const parent of parents) {
    console.log(`Parent: ${parent.path}; development-only: ${parent.dev}`);
  }
  if (!issue.dev || parents.some((parent) => !parent.dev)) {
    console.error("braces may be reachable through a production dependency; block release.");
    violations++;
  }
} else {
  console.log("braces is absent from this lockfile.");
}

console.log("This provenance check is NOT a vulnerability-audit waiver. Full npm audit must pass separately.");
if (violations) process.exitCode = 1;
