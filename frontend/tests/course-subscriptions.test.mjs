import assert from "node:assert/strict";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = await createServer({
  appType: "custom",
  configFile: false,
  root,
  resolve: { alias: { "@": root } },
  server: { middlewareMode: true },
});
after(async () => vite.close());

test("renders two duration choices with distinct working destinations", async () => {
  const { CourseSubscriptionPlans } = await vite.ssrLoadModule("/components/site/course-subscription-plans.tsx");
  const html = renderToStaticMarkup(React.createElement(CourseSubscriptionPlans));
  assert.equal((html.match(/<article\b/g) ?? []).length, 2);
  for (const months of [4, 8]) {
    assert.ok(html.includes(`href="/subscriptions/${months}-months"`));
    assert.ok(html.includes(`Choose ${months} months`));
    assert.ok(html.includes(`${months}-month plan`));
  }
  assert.match(html, /Request course-specific pricing/);
  assert.doesNotMatch(html, /Buy now|Pay now|R\s?\d/);
});

test("homepage subscription section has an accessible heading and explains request status", async () => {
  const { HomeCourseSubscriptions } = await vite.ssrLoadModule("/components/site/course-subscription-plans.tsx");
  const html = renderToStaticMarkup(React.createElement(HomeCourseSubscriptions));
  assert.match(html, /aria-labelledby="course-subscriptions-title"/);
  assert.match(html, /id="course-subscriptions-title"/);
  assert.match(html, /href="\/subscriptions"/);
  assert.match(html, /does not take payment or activate access/);
});

test("unsupported duration routes cannot become a plan", async () => {
  const { getCourseSubscriptionPlan } = await vite.ssrLoadModule("/lib/course-subscriptions.ts");
  assert.equal(getCourseSubscriptionPlan("4-months").months, 4);
  assert.equal(getCourseSubscriptionPlan("8-months").months, 8);
  for (const slug of ["12-months", "4", "", "../checkout", "8-months?price=1"]) {
    assert.equal(getCourseSubscriptionPlan(slug), undefined);
  }
});

test("subscription requests preserve the selected course and duration without inventing a charge", async () => {
  const { getCourseSubscriptionPlan, subscriptionRequestMessage } = await vite.ssrLoadModule("/lib/course-subscriptions.ts");
  const course = { title: "Engineering Mathematics N4", curriculum: "NATED", level: "TVET N4" };
  for (const months of [4, 8]) {
    const message = subscriptionRequestMessage(getCourseSubscriptionPlan(`${months}-months`), course);
    assert.ok(message.includes(`${months}-month course subscription`));
    assert.ok(message.includes("Course: Engineering Mathematics N4"));
    assert.ok(message.includes("Curriculum: NATED"));
    assert.ok(message.includes("Level: TVET N4"));
    assert.match(message, /total price in ZAR/);
    assert.match(message, /before I pay/);
  }
});
