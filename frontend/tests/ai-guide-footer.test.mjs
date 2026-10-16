import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const fromFrontend = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("footer shows a direct Amaris AI Guide link for public visitors", () => {
  const footer = fromFrontend("components/site/footer.tsx");
  assert.match(footer, /href="\/ai-guide"/);
  assert.match(footer, /Amaris AI Guide/);
});

test("AI Guide page includes speech tour, real assistant and contact fallback", () => {
  const page = fromFrontend("app/ai-guide/page.tsx");
  assert.match(page, /<AiGuideTour\s*\/>/);
  assert.match(page, /<AmarisAssistantLauncher\s*\/>/);
  assert.match(page, /href="\/contact"/);
});

test("speaking guide remains usable without speech support", () => {
  const tour = fromFrontend("components/site/ai-guide-tour.tsx");
  assert.match(tour, /speechSynthesis/);
  assert.match(tour, /not supported in this browser/);
  assert.match(tour, /aria-live="polite"/);
});


test("guide exposes clear voice choice and pace controls", () => {
  const tour = fromFrontend("components/site/ai-guide-tour.tsx");
  const assistant = fromFrontend("components/site/amaris-assistant.tsx");
  assert.match(tour, /Best available English voice/);
  assert.match(tour, /Natural \\(recommended\\)/);
  assert.match(tour, /voiceschanged/);
  assert.match(assistant, /selectEnglishVoice/);
  assert.match(assistant, /Best available English voice/);
});
