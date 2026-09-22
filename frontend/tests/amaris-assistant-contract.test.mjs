import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
const component = await readFile(
  new URL("../components/site/amaris-assistant.tsx", import.meta.url),
  "utf8",
);
const route = await readFile(new URL("../app/api/assistant/route.ts", import.meta.url), "utf8");

test("homepage surfaces Amaris Assistant", () => {
  assert.match(home, /<AmarisAssistant\s*\/>/);
  assert.match(home, /components\/site\/amaris-assistant/);
});

test("assistant UI warns clients not to send secrets", () => {
  assert.match(component, /Do not send passwords, card details, OTPs, or other secrets\./);
  assert.match(component, /Answers from website information only/);
});

test("assistant proxy keeps OpenAI credentials off the browser", () => {
  assert.match(route, /CMS_API_URL/);
  assert.match(route, /\/assistant\//);
  assert.doesNotMatch(route, /OPENAI_API_KEY/);
  assert.match(route, /cache:\s*"no-store"/);
});
