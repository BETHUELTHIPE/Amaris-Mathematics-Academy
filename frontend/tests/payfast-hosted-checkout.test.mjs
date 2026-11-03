import assert from "node:assert/strict";
import test, { after } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  appType: "custom",
  configFile: false,
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { payFastHostedAction } = await vite.ssrLoadModule("/lib/payfast-hosted-checkout.ts");
after(() => vite.close());

const fields = {
  merchant_id: "10000100",
  merchant_key: "sandbox-key",
  m_payment_id: "LCB-SYNTHETIC-0001",
  item_name: "Synthetic class booking",
  amount: "250.00",
  signature: "a".repeat(32),
  return_url: "https://example.test/payments/pending",
  cancel_url: "https://example.test/payments/cancelled",
  notify_url: "https://example.test/api/v1/payfast/itn/",
};
const payload = (gateway_url, updates = {}) => ({ gateway_url, fields: { ...fields, ...updates } });

test("only official browser-hosted PayFast URLs can receive signed checkout fields", () => {
  for (const url of [
    "https://sandbox.payfast.co.za/eng/process",
    "https://www.payfast.co.za/eng/process",
  ]) assert.equal(payFastHostedAction(payload(url)), url);
  for (const bad of [
    "https://attacker.example/eng/process",
    "http://sandbox.payfast.co.za/eng/process",
    "https://sandbox.payfast.co.za.evil.invalid/eng/process",
    "https://www.payfast.co.za@evil.invalid/eng/process",
    "https://sandbox.payfast.co.za/eng/process?merchant_id=evil",
    "javascript:alert(1)",
    "https://sandbox.payfast.co.za/onsite/process",
  ]) assert.equal(payFastHostedAction(payload(bad)), null, bad);
});

test("incomplete, unsigned or non-server-priced payloads fail closed before navigation", () => {
  for (const update of [
    { merchant_id: "" }, { merchant_key: "" }, { signature: "" },
    { signature: "not-an-md5-signature" }, { amount: "0.00" }, { amount: "-250.00" },
    { amount: "250" }, { m_payment_id: "" }, { notify_url: "" },
    { notify_url: "http://insecure.example/itn" },
    { cancel_url: "javascript:alert(1)" }, { return_url: "//attacker.example/return" },
  ]) assert.equal(payFastHostedAction(payload("https://sandbox.payfast.co.za/eng/process",update)),null,JSON.stringify(update));
});

test("shared checkout remains interactive, accessible, browser-native and sends fields unchanged", () => {
  const form = readFileSync(new URL("../components/site/payfast-hosted-checkout.tsx",import.meta.url),"utf8");
  assert.match(form, /method="post"/);
  assert.match(form, /target="_self"/);
  assert.match(form, /action=\{action\}/);
  assert.match(form, /type="hidden"/);
  assert.match(form, /name=\{name\}/);
  assert.match(form, /value=\{value\}/);
  assert.match(form, /type="submit"/);
  assert.match(form, /payFastHostedAction\(checkout\)/);
  assert.doesNotMatch(form, /onSubmit=|window\.open\(|<iframe\\b/);
});

test("all course, live class and video checkouts use one validated hosted form", () => {
  for(const path of [
    "../app/checkout/[slug]/page.tsx",
    "../app/book-online-live-class/checkout/page.tsx",
    "../components/site/video-request-form.tsx",
  ]) {
    const source=readFileSync(new URL(path,import.meta.url),"utf8");
    assert.match(source, /<PayFastHostedCheckout checkout=\{checkout\}/,path);
    assert.doesNotMatch(source, /<form method="post" action=\{checkout\.gateway_url\}/,path);
  }
});
