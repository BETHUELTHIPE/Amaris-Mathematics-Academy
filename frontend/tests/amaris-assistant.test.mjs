import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("homepage exposes the website-grounded Amaris Assistant", async () => {
  const [home, component, route] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../components/site/amaris-assistant.tsx", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../app/api/assistant/route.ts", import.meta.url), "utf8"),
  ]);

  assert.match(home, /<AmarisAssistant \/>/);
  assert.match(component, /Amaris Assistant/);
  assert.match(
    component,
    /I answer only from information published on this website\./,
  );
  assert.match(component, /aria-live="polite"/);
  assert.match(component, /Do not share passwords, OTPs, card details or other secrets/);
  assert.match(component, /fetch\("\/api\/assistant"/);

  assert.match(route, /CMS_API_URL/);
  assert.match(route, /\/assistant\/ask\//);
  assert.match(route, /Cache-Control": "no-store"/);
  assert.doesNotMatch(route, /OPENAI_API_KEY/);
});
