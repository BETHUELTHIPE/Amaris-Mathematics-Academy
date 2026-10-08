import assert from "node:assert/strict";
import test from "node:test";
import { verifyBookingPage } from "../scripts/verify-booking-page.mjs";

const html = "Choose your programme, topic and tutor time. Available Zoom slots. R250";
const url = "https://staging.example.com/book-online-live-class";
const silent = { wait: async () => {}, log: () => {} };

test("staging gate survives a cold-start timeout and transient gateway response", async () => {
  let calls = 0;
  await verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => {
      calls += 1;
      if (calls === 1) throw new DOMException("Cold start", "TimeoutError");
      if (calls === 2) return new Response("Starting", { status: 503 });
      return new Response(html);
    },
  });
  assert.equal(calls, 3);
});

test("staging gate fails after bounded retries when the frontend stays unavailable", async () => {
  let calls = 0;
  await assert.rejects(verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => { calls += 1; return new Response("Unavailable", { status: 502 }); },
  }), /remained unavailable/);
  assert.equal(calls, 4);
});

test("staging gate rejects permanent HTTP and page-content failures without retrying", async () => {
  for (const [body, status] of [
    [html, 404],
    [html, 500],
    [`${html} We could not find that page`, 200],
    ["Book online live class", 200],
    [html.replace("R250", "R450"), 200],
  ]) {
    let calls = 0;
    await assert.rejects(verifyBookingPage(url, {
      ...silent,
      fetchPage: async () => { calls += 1; return new Response(body, { status }); },
    }));
    assert.equal(calls, 1);
  }
});

test("staging gate also bounds timeouts while reading the response body", async () => {
  let calls = 0;
  await assert.rejects(verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => {
      calls += 1;
      return { status: 200, text: async () => { throw new DOMException("No body", "TimeoutError"); } };
    },
  }), /cold-start window/);
  assert.equal(calls, 4);
});

test("staging gate ignores unused React fallback data but requires rendered booking text", async () => {
  const fallback = '<script>self.__rsc.push("We could not find that page")</script>';
  await verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => new Response(`<main>${html}</main>${fallback}`),
  });
  await assert.rejects(verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => new Response(`<h1>We could not find that page</h1><script>${html}</script>`),
  }), /branded 404/);
  await assert.rejects(verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => new Response(`<main>Loading</main><script>${html}</script>`),
  }), /missing required content/);
});
