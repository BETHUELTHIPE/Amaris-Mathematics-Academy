// Build a local-only visual fixture using the actual production chart component.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(process.argv[2] || "/tmp/amaris-analytics-preview");
await mkdir(output, { recursive: true });
await build({ entryPoints: [resolve(root, "e2e/fixtures/analytics-preview.tsx")], bundle: true, outdir: output, entryNames: "app", format: "esm", platform: "browser", jsx: "automatic", target: "es2022", minify: true, define: { "process.env.NODE_ENV": '"production"' }, alias: { "@": root } });
const html = '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Amaris analytics design preview · Sample data</title><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>';
await writeFile(resolve(output, "index.html"), html);
for (const route of ["dashboard/analytics", "tutor/analytics"]) {
  await mkdir(resolve(output, route), { recursive: true });
  await writeFile(resolve(output, route, "index.html"), html);
}
process.stdout.write(`Synthetic analytics preview built: ${output}\n`);
