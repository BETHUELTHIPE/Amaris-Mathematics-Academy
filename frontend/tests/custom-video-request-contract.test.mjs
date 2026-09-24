import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path) {
  return readFile(new URL(path, import.meta.url), "utf8");
}

test("custom video wizard exposes the required academic and upload steps", async () => {
  const wizard = await source("../components/site/custom-video-request-wizard.tsx");

  for (const field of ["curriculum", "subject", "grade", "topic", "files"]) {
    assert.match(wizard, new RegExp(`name=["']${field}["']`));
  }
  assert.match(wizard, /multiple/);
  assert.match(wizard, /\.pdf/);
  assert.match(wizard, /\.heic/);
  assert.match(wizard, /\.docx/);
  assert.match(wizard, /Continue to secure payment/);
  assert.match(wizard, /modelled_topics/);
});

test("custom video pricing comes from backend options and checkout, not a hardcoded product fee", async () => {
  const wizard = await source("../components/site/custom-video-request-wizard.tsx");
  const checkout = await source("../app/request-your-own-video/checkout/page.tsx");

  assert.match(wizard, /options\.amount/);
  assert.match(checkout, /checkout\.request\.amount/);
  assert.doesNotMatch(wizard, /R\s*250/);
  assert.doesNotMatch(checkout, /R\s*250/);
});

test("multipart uploads keep browser-generated boundaries", async () => {
  const studentApi = await source("../lib/student-api.ts");

  assert.match(studentApi, /init\.body instanceof FormData/);
  assert.match(studentApi, /!isFormData/);
  assert.match(studentApi, /60_000/);
});

test("custom video navigation is always surfaced", async () => {
  const cms = await source("../lib/cms.ts");

  assert.match(cms, /Request Your Own Video/);
  assert.match(cms, /\/request-your-own-video/);
});

test("confirmation does not trust the browser return as payment proof", async () => {
  const confirmation = await source(
    "../app/request-your-own-video/confirmation/page.tsx",
  );

  assert.match(confirmation, /server-verified PayFast notification/);
  assert.match(confirmation, /invoice_pdf_url/);
});
