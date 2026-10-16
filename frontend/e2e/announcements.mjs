import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = await import(process.env.ANNOUNCEMENTS_PLAYWRIGHT_MODULE || "playwright");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = resolve(process.env.ANNOUNCEMENTS_ARTIFACTS || "/tmp/amaris-announcements");
mkdirSync(artifacts, { recursive: true });
const launch = () => chromium.launch({
  executablePath: process.env.ANNOUNCEMENTS_CHROME_PATH || undefined,
  headless: true,
  args: ["--no-sandbox", ...(process.env.ANNOUNCEMENTS_SINGLE_PROCESS === "true" ? ["--disable-gpu", "--no-zygote", "--single-process"] : [])],
});

// Synthetic notices only. Never connect this harness to the live CMS or Auth.
const fixture = [
  { id: 3, title: "Plan your next Mathematics session", message: "Choose a topic, find an available tutor time, and take your next step with confidence.\nSelect your programme and level before choosing a class.", link_url: "/book-online-live-class", link_label: "Explore live classes", priority: 2, expires_at: "2099-12-31T10:00:00Z" },
  { id: 2, title: "A focused path through your course", message: 'Explore your programme. <script>alert("example")</script>', link_url: "/courses", link_label: "Find your course", priority: 0, expires_at: null },
  { id: 1, title: "Keep your account details private", message: "For account or payment questions, contact the academy directly.", link_url: "javascript:alert(1)", link_label: "Unsafe fixture", priority: 0, expires_at: null },
  { id: 0, title: "EXPIRED NOTICE", message: "Must not appear", link_url: "", link_label: "", priority: 10, expires_at: "2020-01-01T00:00:00Z" },
];
const cms = http.createServer((request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url.includes("bootstrap")) return response.end(JSON.stringify({ settings: null, navigation: [] }));
  if (request.url.startsWith("/outage/")) { response.statusCode = 503; return response.end("{}"); }
  response.end(JSON.stringify(request.url.startsWith("/empty/") ? [] : fixture));
});
const wait = (ms) => new Promise((done) => setTimeout(done, ms));

await new Promise((done) => cms.listen(4312, "127.0.0.1", done));
let browser;
try {
  for (const [index, mode] of ["normal", "empty", "outage"].entries()) {
    const port = 4320 + index;
    const origin = `http://127.0.0.1:${port}`;
    const server = spawn(process.execPath, [".output/server/index.mjs"], {
      cwd: root,
      env: { ...process.env, NODE_ENV: "production", HOST: "127.0.0.1", PORT: String(port), CMS_API_URL: `http://127.0.0.1:4312/${mode}` },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let logs = "";
    server.stdout.on("data", (data) => { logs += data; });
    server.stderr.on("data", (data) => { logs += data; });
    try {
      let ready = false;
      for (let attempt = 0; attempt < 60; attempt++) {
        try { await fetch(`${origin}/announcements`); ready = true; break; } catch { await wait(250); }
      }
      assert.ok(ready, `Frontend failed to start: ${logs}`);
      browser = await launch();
      const context = await browser.newContext({ javaScriptEnabled: false });
      const page = await context.newPage();
      const response = await page.goto(`${origin}/announcements`);
      assert.equal(response.status(), 200, logs);
      await page.getByRole("heading", { name: "Stay informed. Keep moving forward." }).waitFor();
      if (mode === "normal") {
        await page.getByRole("heading", { name: fixture[0].title }).waitFor();
        assert.equal(await page.getByText("EXPIRED NOTICE", { exact: true }).count(), 0);
        assert.equal(await page.getByRole("link", { name: "Unsafe fixture" }).count(), 0);
        await page.getByLabel("Search academy notices").fill("account");
        await page.getByLabel("Search academy notices").press("Enter");
        assert.equal(await page.locator("article").count(), 1);
        await page.getByRole("link", { name: /Clear filters/ }).press("Enter");
        await page.getByRole("navigation", { name: "Announcement filters" }).getByRole("link", { name: /Priority notices/ }).press("Enter");
        assert.equal(await page.locator("article").count(), 1);
        await page.goto(`${origin}/announcements?q=nomatch`);
        await page.getByRole("heading", { name: "No notices match just yet." }).waitFor();
        await page.goto(`${origin}/announcements`);
      } else {
        await page.getByRole("heading", { name: mode === "empty" ? "A quiet noticeboard. A clear path ahead." : "We couldn’t load the notices." }).waitFor();
      }
      for (const width of [320, 390, 834, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        const sizes = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, width: innerWidth }));
        assert.ok(sizes.doc <= sizes.width, `${mode} at ${width}: horizontal overflow`);
        if (mode === "normal" && [390, 1440].includes(width)) {
          await page.screenshot({ path: `${artifacts}/announcements-${width}.png`, fullPage: true });
        }
      }
      // Separate launches also support restricted single-process Chromium.
      await browser.close();
      browser = await launch();
      const enhanced = await browser.newContext();
      const enhancedPage = await enhanced.newPage();
      const errors = [];
      enhancedPage.on("pageerror", (error) => errors.push(error.message));
      await enhancedPage.goto(`${origin}/announcements`);
      await enhancedPage.addScriptTag({ path: `${root}/node_modules/axe-core/axe.min.js` });
      const violations = await enhancedPage.evaluate(async () => (await axe.run(document.querySelector("main"), {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
      })).violations.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => node.target) })));
      assert.deepEqual(violations, []);
      assert.deepEqual(errors, []);
      await enhancedPage.keyboard.press("Tab");
      assert.notEqual(await enhancedPage.evaluate(() => document.activeElement.tagName), "BODY");
      await browser.close();
      browser = undefined;
      console.log(`${mode}: PASS — native search/filter (when populated), four viewport checks, Axe, keyboard focus and hydration`);
    } finally {
      server.kill();
    }
  }
} finally {
  await browser?.close();
  cms.close();
}
