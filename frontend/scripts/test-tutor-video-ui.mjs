import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.resolve(frontend, "..");
const fixture = process.env.TUTOR_UI_FIXTURE;
assert.ok(fixture, "Provide the isolated UI fixture directory");
const require = createRequire(path.join(fixture, "package.json"));
const { chromium } = require("playwright");
const esbuild = require("esbuild");
const component = path.join(frontend, "components/tutor/video-upload-form.tsx");
await writeFile(path.join(fixture, "entry.tsx"), `import {createRoot} from "react-dom/client";\nimport {TutorVideoUploadForm} from ${JSON.stringify(component)};\ncreateRoot(document.getElementById("root")).render(<main className="mx-auto max-w-4xl px-5 py-8"><p className="mb-5 text-sm">Tutor workspace preview - synthetic test data</p><TutorVideoUploadForm maxBytes={52428800}/></main>);`);
await writeFile(path.join(fixture, "input.css"), `@import "tailwindcss";\n@source "./entry.tsx";\n@source ${JSON.stringify(component)};\nbody{font-family:Arial,sans-serif;background:#f5f7fb;color:#07152d}.eyebrow{font-size:12px;color:#1f5bbd;font-weight:bold;text-transform:uppercase;letter-spacing:1.5px}`);
esbuild.buildSync({ entryPoints: [path.join(fixture, "entry.tsx")], outfile: path.join(fixture, "bundle.js"), bundle: true, format: "esm", jsx: "automatic", nodePaths: [path.join(fixture, "node_modules")] });
execFileSync(path.join(fixture, "node_modules/.bin/tailwindcss"), ["-i", path.join(fixture, "input.css"), "-o", path.join(fixture, "style.css")]);
const html = '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tutor video fixture</title><link href="/style.css" rel="stylesheet"></head><body><div id="root"></div><script type="module" src="/bundle.js"></script></body></html>';
const server = createServer(async (request, response) => {
  const file = { "/": ["text/html", html], "/bundle.js": ["text/javascript", await readFile(path.join(fixture, "bundle.js"))], "/style.css": ["text/css", await readFile(path.join(fixture, "style.css"))] }[request.url];
  if (!file) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { "Content-Type": file[0] }); response.end(file[1]);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
let page;
try {
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const keys = [];
  await page.route("**/api/tutor/videos", async route => {
    const body = route.request().postDataBuffer().toString("utf8");
    keys.push(body.match(/name="idempotency_key"\r\n\r\n([^\r]+)/)?.[1]);
    if (keys.length === 1) await route.abort("failed");
    else await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ activity_reference: "SYNTHETIC-UI-TEST" }) });
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByLabel("Video title", { exact: true }).fill("Quadratic equations");
  await page.getByLabel("Curriculum", { exact: true }).selectOption("caps");
  await page.getByLabel("Subject", { exact: true }).selectOption("mathematics");
  await page.getByLabel("Grade, level or module", { exact: true }).fill("Grade 11");
  await page.getByLabel("Topic", { exact: true }).fill("Factorisation");
  await page.getByLabel("Lesson video").setInputFiles({ name: "lesson.mp4", mimeType: "video/mp4", buffer: Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 105, 115, 111, 109, 1]) });
  await page.getByRole("button", { name: "Submit video for review" }).click();
  await page.getByRole("alert").filter({ hasText: "connection was interrupted" }).waitFor();
  await page.getByRole("button", { name: "Submit video for review" }).click();
  await page.getByRole("status").filter({ hasText: "SYNTHETIC-UI-TEST" }).waitFor();
  assert.equal(keys.length, 2); assert.ok(keys[0]); assert.equal(keys[0], keys[1]);
  assert.equal(await page.getByLabel("Video title", { exact: true }).inputValue(), "");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
  await mkdir(path.join(root, "artifacts"), { recursive: true });
  await page.screenshot({ path: path.join(root, "artifacts/tutor-video-ui-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.screenshot({ path: path.join(root, "artifacts/tutor-video-ui-desktop.png"), fullPage: true });
  console.log("PASS actual React/Tailwind form: mobile/desktop, multipart, same-key interrupted retry, success/reset and no mobile overflow; synthetic backend responses only");
} catch (error) {
  await mkdir(path.join(root, "artifacts"), { recursive: true });
  if (page) await page.screenshot({ path: path.join(root, "artifacts/tutor-video-ui-failed.png"), fullPage: true }).catch(() => {});
  throw error;
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
