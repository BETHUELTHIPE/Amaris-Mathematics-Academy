import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  appType: "custom", configFile: false, root,
  plugins: [{
    name: "isolated-contact-storage", enforce: "pre",
    resolveId(id) {
      if (id === "@/lib/location-server" || id === "@/lib/location-data") return fileURLToPath(new URL("../lib/" + id.split("/").at(-1) + ".ts", import.meta.url)); 
      if (id === "cloudflare:workers") return "\0test:contact-env";
      if (id === "@/db") return "\0test:contact-db";
      if (id === "@/lib/contact-validation") return fileURLToPath(new URL("../lib/contact-validation.ts", import.meta.url));
    },
    load(id) {
      if (id === "\0test:contact-env") return 'export const env = {};';
      if (id === "\0test:contact-db") return 'export function getD1() { throw new Error("Invalid enquiries must not reach storage"); }';
    },
  }],
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { submitEnquiry } = await vite.ssrLoadModule("/app/contact/actions.ts");
const { contactRequiredMessages } = await vite.ssrLoadModule("/lib/contact-validation.ts");
after(() => vite.close());
const originalFetch = globalThis.fetch;
const originalCmsUrl = process.env.CMS_API_URL;
let calls;
beforeEach(() => {
  calls = [];
  process.env.CMS_API_URL = "https://cms.example.test/api/v1";
  globalThis.fetch = async (...args) => { calls.push(args); return new Response("{}", { status: 201 }); };
});
after(() => {
  globalThis.fetch = originalFetch;
  if (originalCmsUrl === undefined) delete process.env.CMS_API_URL;
  else process.env.CMS_API_URL = originalCmsUrl;
});

function enquiry() {
  const form = new FormData();
  for (const [key, value] of Object.entries({ fullName: "Synthetic Student", country: "ZA", province: "Gauteng", city: "Pretoria", email: "student@example.test", phone: "+27 71 000 0000", enquiryType: "technical-support", message: "Please help me choose the correct mathematics course.", consent: "on" })) form.set(key, value);
  return form;
}

test("each omitted, empty or whitespace field returns its named prompt without sending", async () => {
  for (const [field, message] of Object.entries(contactRequiredMessages)) {
    for (const value of [null, "", "   ", "\t\n"]) {
      const form = enquiry();
      if (value === null) form.delete(field);
      else form.set(field, value);
      const result = await submitEnquiry({ status: "idle" }, form);
      assert.equal(result.status, "error");
      assert.equal(result.errors[field], message, `${field}: ${JSON.stringify(value)}`);
      assert.equal(calls.length, 0);
    }
  }
});

test("an empty contact form identifies all nine visible fields", async () => {
  const result = await submitEnquiry({ status: "idle" }, new FormData());
  assert.deepEqual(Object.keys(result.errors).sort(), Object.keys(contactRequiredMessages).sort());
  assert.equal(calls.length, 0);
});

test("invalid email and short message remain rejected after required fields are supplied", async () => {
  for (const [field, value] of [["email", "invalid"], ["message", "too short"]]) {
    const form = enquiry();
    form.set(field, value);
    const result = await submitEnquiry({ status: "idle" }, form);
    assert.equal(result.status, "error");
    assert.ok(result.errors[field]);
  }
  assert.equal(calls.length, 0);
});

test("a corrected complete form submits the phone number to Django", async () => {
  const result = await submitEnquiry({ status: "error" }, enquiry());
  assert.equal(result.status, "success");
  assert.equal(calls.length, 1);
  assert.equal(JSON.parse(calls[0][1].body).phone, "+27 71 000 0000");
});

test("unlisted locations keep explicit Other markers when sent to Django", async () => {
  const form = enquiry();
  form.set("province", "__other__"); form.set("provinceOther", "Synthetic region");
  form.set("city", "__other__"); form.set("cityOther", "Synthetic town");
  form.set("cityOther", "   ");
  const invalid = await submitEnquiry({ status: "idle" }, form);
  assert.equal(invalid.errors.cityOther, "Please enter your city or town.");
  assert.equal(calls.length, 0);
  form.set("cityOther", "Synthetic town");
  assert.equal((await submitEnquiry({ status: "idle" }, form)).status, "success");
  const body = JSON.parse(calls[0][1].body);
  assert.equal(body.province, "__other__"); assert.equal(body.provinceOther, "Synthetic region");
  assert.equal(body.city, "__other__"); assert.equal(body.cityOther, "Synthetic town");
});
