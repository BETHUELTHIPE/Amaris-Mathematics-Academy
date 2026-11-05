import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path) { return readFile(new URL(path, import.meta.url), "utf8"); }

test("payment and working policies use the shared company letterhead and footer", async () => {
  const policy = await source("../components/site/policy-page.tsx");
  const brand = await source("../components/documents/brand-letterhead.tsx");
  assert.match(policy, /BrandLetterhead documentLabel=\{policy\.title\}/);
  assert.match(policy, /BrandDocumentFooter reference=\{policy\.title\}/);
  assert.match(policy, /\/policies\/\$\{kind\}-policy\.pdf/);
  assert.match(brand, /academyBrand\.logoPath/);
  assert.match(brand, /academyBrand\.email/);
});

test("invoice documents retain the same company letterhead", async () => {
  const invoice = await source("../components/documents/invoice-document.tsx");
  assert.match(invoice, /<BrandLetterhead documentLabel="Invoice"/);
  assert.match(invoice, /<BrandDocumentFooter/);
});
