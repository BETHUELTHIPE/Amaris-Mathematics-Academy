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

test("all official account email templates carry the approved letterhead and preserve security tokens", async () => {
  const names = ["confirm-signup", "magic-link-login", "recovery"];
  for (const name of names) {
    const html = await source(`../email-templates/${name}.html`);
    assert.match(html, /Amaris Mathematics Academy/);
    assert.match(html, /amaris-academy-icon-192\.png/);
    assert.match(html, /MATHEMATICS · LEARNING · PROGRESS/);
    assert.match(html, /27 Tshivhase Street/);
    assert.match(html, /071 415 6665/);
    assert.match(html, /bethuelmoukangwe8@gmail\.com/);
    assert.match(html, /Professional mathematics education and learner support/);
    assert.match(html, /{{ \.Token }}/);
    assert.doesNotMatch(html, /localhost:3000/);
  }
  const confirmation = await source("../email-templates/confirm-signup.html");
  const login = await source("../email-templates/magic-link-login.html");
  const recovery = await source("../email-templates/recovery.html");
  assert.match(confirmation, /{{ \.ConfirmationURL }}/);
  assert.match(login, /{{ \.ConfirmationURL }}/);
  assert.match(recovery, /{{ \.TokenHash }}/);
  assert.match(recovery, /{{ \.RedirectTo }}/);
});

test("Django formal correspondence uses the approved letterhead without generic unbranded emails", async () => {
  const tasks = await source("../../backend/content/tasks.py");
  const enquiry = await source("../../backend/content/services/enquiry_autoreply.py");
  const letterhead = await source("../../backend/content/services/official_letterhead.py");
  const invoice = await source("../../backend/content/services/invoices.py");
  const archive = await source("../../backend/content/services/course_invoice_archive.py");
  assert.match(tasks, /official_letterhead_html/);
  assert.match(tasks, /email\.attach_alternative\(/);
  assert.match(tasks, /message\.attach_alternative\(html, "text\/html"\)/);
  assert.match(enquiry, /official_letterhead_html/);
  assert.match(enquiry, /message\.attach_alternative\(/);
  assert.match(letterhead, /Amaris Mathematics Academy/);
  assert.match(letterhead, /amaris-academy-icon-192\.png/);
  assert.match(invoice, /site\.logo/);
  assert.match(archive, /site\.logo/);
});
