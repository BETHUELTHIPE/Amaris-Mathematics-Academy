import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

test("renders development preview metadata", async (t) => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  let worker;
  try {
    ({ default: worker } = await import(workerUrl.href));
  } catch (error) {
    if (error?.code === "ERR_UNSUPPORTED_ESM_URL_SCHEME") {
      t.skip("The plain Node test runner cannot load the Cloudflare runtime module.");
      return;
    }
    throw error;
  }

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
  assert.match(await response.text(), developmentPreviewMeta);
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
