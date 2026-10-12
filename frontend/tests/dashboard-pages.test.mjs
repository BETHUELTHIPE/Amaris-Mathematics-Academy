import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const dependencies = new Set(["@/lib/auth", "@/lib/student-api", "test:dashboard"]);
const vite = await createServer({
  configFile: false, root, appType: "custom",
  plugins: [{
    name: "dashboard-test-data", enforce: "pre",
    resolveId(id) {
      if (dependencies.has(id)) return "\0dashboard-test-data";
      if (id === "@/components/site/header" || id === "@/components/site/footer") return "\0dashboard-chrome";
      if (id === "next/link") return "\0dashboard-link";
      if (id.startsWith("@/")) return this.resolve(`${root}${id.slice(2)}`, undefined, { skipSelf: true });
    },
    load(id) {
      if (id === "\0dashboard-chrome") return "export function Header() { return null; } export function Footer() { return null; }";
      if (id === "\0dashboard-link") return 'import {createElement} from "react"; export default function Link(props) {return createElement("a", props);}';
      if (id === "\0dashboard-test-data") return `
        export const state = {};
        export async function requireVerifiedStudent(path) {
          state.returnTo = path;
          if (state.denied) throw new Error("authentication required");
        }
        export async function getStudentOrders() {
          state.fetched = true;
          if (state.unavailable) throw new Error("private upstream details");
          return state.orders;
        }
        export async function getStudentNotifications() {
          state.fetched = true;
          if (state.unavailable) throw new Error("private upstream details");
          return state.notifications;
        }
      `;
    },
  }],
  server: { middlewareMode: true, hmr: false, ws: false },
});
const { state } = await vite.ssrLoadModule("test:dashboard");
const { default: Orders } = await vite.ssrLoadModule("/app/dashboard/orders/page.tsx");
const { default: Notifications } = await vite.ssrLoadModule("/app/dashboard/notifications/page.tsx");
after(() => vite.close());
beforeEach(() => {
  for (const key of Object.keys(state)) delete state[key];
  state.orders = [];
  state.notifications = [];
});

test("orders render real statuses, amounts and the invoice destination for each purchase type", async () => {
  state.orders = ["course", "live_class", "video_request"].map((kind) => ({
    kind, reference: `${kind}-001`, title: `Mathematics ${kind}`, detail: "Student order",
    amount: "250.00", currency: "ZAR", status: "paid", status_label: "Paid",
    created_at: "2026-10-12T12:00:00Z", paid_at: "2026-10-12T12:01:00Z",
    invoice_number: `INV-${kind}`, invoice_ready: true, href: "/courses/mathematics",
  }));
  const html = renderToStaticMarkup(await Orders());
  assert.equal(state.returnTo, "/dashboard/orders");
  for (const [kind, path] of [["course", "/dashboard/orders/invoice"], ["live_class", "/book-online-live-class/invoice"], ["video_request", "/request-a-video/invoice"]]) {
    assert.ok(html.includes(`href="${path}?reference=${kind}-001"`));
    assert.ok(html.includes(`INV-${kind}`));
  }
  assert.match(html, /250[.,]00/);
  assert.match(html, /Paid/);
  assert.doesNotMatch(html, /No orders yet/);
  state.orders[0].invoice_ready = false;
  assert.doesNotMatch(renderToStaticMarkup(await Orders()), /href="\/dashboard\/orders\/invoice/);
});

test("notifications render the student's update and its destination", async () => {
  state.notifications = [{ id: "payment-1", title: "Payment confirmation", message: "Algebra: Paid.", delivery_status: "Sent", occurred_at: "2026-10-12T12:00:00Z", href: "/dashboard/orders" }];
  const html = renderToStaticMarkup(await Notifications());
  assert.equal(state.returnTo, "/dashboard/notifications");
  assert.match(html, /Algebra: Paid\./);
  assert.match(html, /href="\/dashboard\/orders"/);
  assert.doesNotMatch(html, /caught up/);
});

for (const [name, Page, empty] of [["orders", Orders, /No orders yet/], ["notifications", Notifications, /caught up/]]) {
  test(`${name} distinguishes an empty account from an unavailable service`, async () => {
    assert.match(renderToStaticMarkup(await Page()), empty);
    state.unavailable = true;
    const html = renderToStaticMarkup(await Page());
    assert.match(html, /role="alert"/);
    assert.match(html, /temporarily unavailable/);
    assert.doesNotMatch(html, empty);
    assert.doesNotMatch(html, /private upstream details/);
  });

  test(`${name} requires authentication before fetching student data`, async () => {
    state.denied = true;
    await assert.rejects(Page(), /authentication required/);
    assert.equal(state.fetched, undefined);
  });
}

test("short dashboard URLs redirect to their protected pages", async () => {
  for (const path of ["orders", "notifications"]) {
    const { default: Page } = await vite.ssrLoadModule(`/app/${path}/page.tsx`);
    assert.throws(Page, (error) => error.digest?.split(";")[2] === `/dashboard/${path}`);
  }
});
