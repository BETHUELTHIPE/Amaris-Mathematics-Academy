import assert from "node:assert/strict";
import test from "node:test";
import { verifyBookingPage } from "../scripts/verify-booking-page.mjs";

const url = "https://staging.example.com/book-online-live-class";
const safeLogin = "/login?next=%2Fbook-online-live-class";
const silent = { wait: async () => {}, log: () => {} };

function redirect(location = safeLogin, status = 307) {
  return new Response(null, { status, headers: { Location: location } });
}

test("anonymous booking gate sends guests to login and preserves safe booking path", async () => {
  await verifyBookingPage(url, { ...silent, fetchPage: async (_, options) => {
    assert.equal(options.redirect, "manual");
    return redirect();
  } });
});

test("auth gate tolerates cold starts and transient bad gateways", async () => {
  let calls = 0;
  await verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => {
      calls += 1;
      if (calls === 1) throw new DOMException("Cold start", "TimeoutError");
      if (calls === 2) return new Response("Starting", { status: 503 });
      return redirect();
    },
  });
  assert.equal(calls, 3);
});

test("auth gate fails closed after repeated errors", async () => {
  let calls = 0;
  await assert.rejects(verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => { calls += 1; return new Response("Unavailable", { status: 502 }); },
  }), /remained unavailable/);
  assert.equal(calls, 4);
});

test("public booking page exposure, invalid redirects and open redirects all fail the gate", async () => {
  const bad = [
    new Response("Choose your programme, topic and tutor time. Available Zoom slots R250", { status: 200 }),
    new Response("Unavailable", { status: 404 }),
    redirect("/dashboard"),
    redirect("/login?next=%2Fcheckout"),
    redirect("/login?next=https%3A%2F%2Fattacker.example%2Fbook-online-live-class"),
    redirect("https://attacker.example/login?next=%2Fbook-online-live-class"),
    redirect("/login"),
    redirect("/login?next=%2Fbook-online-live-class-impersonation"),
  ];
  for (const result of bad) {
    let calls = 0;
    await assert.rejects(verifyBookingPage(url, {
      ...silent,
      fetchPage: async () => { calls += 1; return result; },
    }), /bypassed or returned an unsafe login redirect/);
    assert.equal(calls, 1);
  }
});

test("guest booking filter choices can be preserved safely on redirect", async () => {
  const filtered = url + "?programme=caps&subject=mathematics";
  await verifyBookingPage(filtered, {
    ...silent,
    fetchPage: async () => redirect("/login?next=%2Fbook-online-live-class%3Fprogramme%3Dcaps%26subject%3Dmathematics"),
  });
});

test("anonymous booking probe never reads the response body", async () => {
  await verifyBookingPage(url, {
    ...silent,
    fetchPage: async () => ({
      status: 307,
      headers: new Headers({ location: safeLogin }),
      text: async () => { throw new Error("No private content should be fetched"); },
    }),
  });
});
