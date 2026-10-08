import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  appType: "custom", configFile: false, root,
  plugins: [{
    name: "isolated-contact-bindings", enforce: "pre",
    resolveId(id) {
      if (id === "cloudflare:workers") return "\0test:contact-env";
      if (id === "@/db") throw new Error("Contact submissions must not use D1");
    },
    load(id) { if (id === "\0test:contact-env") return "export const env = {};"; },
  }],
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { env } = await vite.ssrLoadModule("cloudflare:workers");
const { submitEnquiry } = await vite.ssrLoadModule("/app/contact/actions.ts");
after(() => vite.close());
beforeEach(() => { env.CMS_API_URL = "https://cms.example.test/api/v1/"; });

function enquiry(overrides = {}) {
  const form = new FormData();
  for (const [key, value] of Object.entries({
    fullName: " Synthetic Student ", email: " Student@Example.test ", phone: "0710000000",
    enquiryType: "course-guidance", message: "Please help with a synthetic course enquiry.",
    consent: "on", website: "", ...overrides,
  })) form.set(key, value);
  return form;
}

test("contact submission reaches the CMS with normalized fields before reporting success", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("{}", { status: 201 }));
  assert.equal((await submitEnquiry({}, enquiry())).status, "success");
  assert.equal(fetch.mock.calls.length, 1);
  const [url, request] = fetch.mock.calls[0].arguments;
  assert.equal(url, "https://cms.example.test/api/v1/enquiries/");
  assert.deepEqual(JSON.parse(request.body), {
    name: "Synthetic Student", email: "student@example.test", phone: "0710000000",
    subject: "course guidance", message: "Please help with a synthetic course enquiry.",
  });
});

test("rejected and unavailable CMS writes never report success or leak provider errors", async (t) => {
  const log = t.mock.method(console, "error", () => {});
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("private provider details", { status: 503 }));
  assert.equal((await submitEnquiry({}, enquiry())).status, "error");
  fetch.mock.mockImplementation(async () => { throw new Error("private network details"); });
  assert.equal((await submitEnquiry({}, enquiry())).status, "error");
  assert.doesNotMatch(JSON.stringify(log.mock.calls.map(call => call.arguments)), /private|student@example/);
});

test("missing CMS configuration never falls back to another database", async (t) => {
  t.mock.method(console, "error", () => {});
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new Error("must not fetch"); });
  delete env.CMS_API_URL;
  const previous = process.env.CMS_API_URL;
  delete process.env.CMS_API_URL;
  try {
    assert.equal((await submitEnquiry({}, enquiry())).status, "error");
    assert.equal(fetch.mock.calls.length, 0);
  } finally {
    if (previous !== undefined) process.env.CMS_API_URL = previous;
  }
});

test("invalid input never reaches the CMS", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new Error("must not fetch"); });
  for (const values of [{ email: "invalid" }, { consent: "" }, { website: "bot" }]) {
    assert.equal((await submitEnquiry({}, enquiry(values))).status, "error");
  }
  assert.equal(fetch.mock.calls.length, 0);
});
