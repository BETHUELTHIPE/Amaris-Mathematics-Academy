import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

async function readTextTree(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const contents = await Promise.all(
    entries.map(async (entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return readTextTree(path);
      try {
        return await readFile(path, "utf8");
      } catch {
        return "";
      }
    }),
  );
  return contents.join("\n");
}

async function assertBuiltOutputHasNoDevelopmentPreviewMarker() {
  const dist = fileURLToPath(new URL("../dist", import.meta.url));
  const builtOutput = await readTextTree(dist);
  assert.doesNotMatch(builtOutput, /codex-preview/i);
}

test("does not leak development preview metadata in the production render", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);

  try {
    const { default: worker } = await import(workerUrl.href);
    const response = await worker.fetch(
      new Request("http://localhost/", {
        headers: { accept: "text/html" },
      }),
      {
        ASSETS: {
          fetch: async () => new Response("Not found", { status: 404 }),
        },
      },
      {
        waitUntil() {},
        passThroughOnException() {},
      },
    );

    assert.equal(response.status, 200);
    assert.match(
      response.headers.get("content-type") ?? "",
      /^text\/html\b/i,
    );
    assert.doesNotMatch(await response.text(), developmentPreviewMeta);
  } catch (error) {
    if (error?.code !== "ERR_UNSUPPORTED_ESM_URL_SCHEME") throw error;
    await assertBuiltOutputHasNoDevelopmentPreviewMarker();
  }
});

test("renders branded recovery pages without technical details", async () => {
  const recoverySource = await readFile(new URL("../lib/recovery.ts", import.meta.url), "utf8");
  const screenSource = await readFile(new URL("../components/site/recovery-screen.tsx", import.meta.url), "utf8");
  const actionsSource = await readFile(new URL("../components/site/recovery-actions.tsx", import.meta.url), "utf8");

  for (const expected of [
    "Let’s try that again.",
    "You do not have access to this page.",
    "Too many attempts were made.",
    "One of our services did not respond.",
    "We’ll be back shortly.",
    "Your payment is still being confirmed.",
    "No payment was completed.",
    "PayFast could not complete the payment.",
    "Please log in again.",
    "You appear to be offline.",
  ]) {
    assert.match(recoverySource, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), expected);
  }
  assert.match(actionsSource, /Support reference/);
  assert.doesNotMatch(`${recoverySource}\n${screenSource}\n${actionsSource}`, /SUPABASE_SERVICE_ROLE|stack trace/i);
});

test("keeps the optimized hero background photo visible on the homepage", async () => {
  const homepageSource = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(homepageSource, /src="\/amaris-math-hero\.webp"/);
  assert.match(homepageSource, /opacity-90/);
});

test("protected application responses are never publicly cacheable", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("cache-test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/checkout", {
      method: "POST",
      headers: { "cf-connecting-ip": "203.0.113.10" },
    }),
    {
      CHECKOUT_RATE_LIMITER: {
        limit: async () => ({ success: false }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 429);
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.match(response.headers.get("vary") ?? "", /Cookie/i);
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");

  const workerSource = await readFile(new URL("../worker/index.ts", import.meta.url), "utf8");
  for (const prefix of ["/dashboard", "/documents", "/checkout", "/api/auth-state"]) {
    assert.ok(workerSource.includes(prefix), `Missing protected prefix ${prefix}`);
  }
});


test("keeps the founder Facebook profile link on the About page", async () => {
  const aboutSource = await readFile(new URL("../app/about/page.tsx", import.meta.url), "utf8");
  assert.match(aboutSource, /https:\/\/www\.facebook\.com\/share\/19dqWUxjvh/);
  assert.match(aboutSource, /label: "Facebook"/);
});
