import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
const component = await readFile(
  new URL("../components/site/amaris-assistant.tsx", import.meta.url),
  "utf8",
);
const launcher = await readFile(
  new URL("../components/site/amaris-assistant-launcher.tsx", import.meta.url),
  "utf8",
);
const route = await readFile(new URL("../app/api/assistant/route.ts", import.meta.url), "utf8");

test("homepage surfaces Amaris Assistant without loading the full client on first paint", () => {
  assert.match(home, /<AmarisAssistantLauncher\s*\/>/);
  assert.match(home, /components\/site\/amaris-assistant-launcher/);
  assert.match(launcher, /import\("\.\/amaris-assistant"\)/);
  assert.match(launcher, /<Assistant initialOpen\s*\/>/);
});

test("assistant requires the user to choose chat or voice mode", () => {
  assert.match(component, /type AssistantMode = "chat" \| "voice"/);
  assert.match(component, /How would you like to use Amaris Assistant\?/);
  assert.match(component, /Chat assistant/);
  assert.match(component, /Voice assistant/);
  assert.match(component, /Choose assistant mode/);
  assert.match(component, /Change mode/);
});

test("voice mode uses browser speech input and reads the GPT answer aloud", () => {
  assert.match(component, /SpeechRecognition/);
  assert.match(component, /webkitSpeechRecognition/);
  assert.match(component, /speechSynthesis\.speak/);
  assert.match(component, /SpeechSynthesisUtterance/);
  assert.match(component, /hear the GPT response/);
  assert.match(component, /role="alert"/);
});

test("assistant UI warns clients not to send secrets", () => {
  assert.match(component, /Do not send passwords, card details, OTPs, or other secrets\./);
  assert.match(component, /Do not speak passwords, card details, OTPs, or other secrets\./);
  assert.match(component, /Answers from website information only/);
});

test("assistant proxy keeps OpenAI credentials off the browser", () => {
  assert.match(route, /CMS_API_URL/);
  assert.match(route, /\/assistant\//);
  assert.doesNotMatch(route, /OPENAI_API_KEY/);
  assert.doesNotMatch(component, /OPENAI_API_KEY/);
  assert.match(route, /cache:\s*"no-store"/);
});

test("course-selection fallback covers catalogue and private-status safety", () => {
  assert.match(route, /const courses =/);
  assert.match(route, /To choose a course, visit \/courses/);
  assert.match(route, /Continue to enrol/);
  assert.match(route, /purchased course appears in \/dashboard/);
  assert.match(route, /my course access/);
  assert.match(route, /payment status/);
});

test("known registration and lesson facts remain available during provider outages", () => {
  assert.match(route, /function publishedAnswer/);
  assert.match(route, /\/register/);
  assert.match(route, /R250 per hour/);
  assert.match(route, /\/book-online-live-class/);
  assert.match(route, /normalizeCmsApiBaseUrl/);
  assert.match(route, /response\.status >= 500 && fallback/);
  assert.match(route, /response\.status === 429/);
  assert.doesNotMatch(route, /OPENAI_API_KEY/);
});
