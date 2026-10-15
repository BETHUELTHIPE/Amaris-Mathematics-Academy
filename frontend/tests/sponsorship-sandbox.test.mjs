import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { stripTypeScriptTypes } from "node:module";
import { createHash } from "node:crypto";

const source = (await readFile(new URL("../lib/sponsorship-sandbox.ts", import.meta.url), "utf8"))
  .replace('"./sponsorship"', JSON.stringify(new URL("../lib/sponsorship.ts", import.meta.url).href));
const { createSandboxSponsorship } = await import(`data:text/javascript;base64,${Buffer.from(stripTypeScriptTypes(source)).toString("base64")}`);

test("sandbox checkout is signed, isolated from live payments and never sends the passphrase", () => {
  const names = ["PAYFAST_SPONSOR_MODE", "PAYFAST_SPONSOR_SANDBOX_MERCHANT_ID", "PAYFAST_SPONSOR_SANDBOX_MERCHANT_KEY", "PAYFAST_SPONSOR_SANDBOX_PASSPHRASE"];
  const previous = names.map(name => process.env[name]);
  try {
    names.forEach(name => delete process.env[name]);
    const checkout = createSandboxSponsorship("100", "https://academy.example");
    assert.equal(checkout.gatewayUrl, "https://sandbox.payfast.co.za/eng/process");
    assert.equal(checkout.fields.amount, "100.00");
    assert.equal(checkout.fields.return_url, "https://academy.example/sponsors/test-result?state=returned");
    assert.equal(checkout.fields.passphrase, undefined);
    assert.equal(checkout.fields.notify_url, undefined);
    const encode = value => new URLSearchParams({ value }).toString().slice(6).replace(/\*/g, "%2A");
    const payload = Object.entries(checkout.fields).filter(([name]) => name !== "signature").map(([name, value]) => `${name}=${encode(value)}`).join("&");
    assert.equal(checkout.fields.signature, createHash("md5").update(`${payload}&passphrase=jt7NOE43FZPn`).digest("hex"));
    assert.throws(() => createSandboxSponsorship("0", "https://academy.example"));
    process.env.PAYFAST_SPONSOR_SANDBOX_PASSPHRASE = "example-test-only";
    assert.throws(() => createSandboxSponsorship("100", "https://academy.example"));
    process.env.PAYFAST_SPONSOR_MODE = "live";
    assert.throws(() => createSandboxSponsorship("100", "https://academy.example"));
  } finally {
    names.forEach((name, index) => previous[index] === undefined ? delete process.env[name] : process.env[name] = previous[index]);
  }
});
