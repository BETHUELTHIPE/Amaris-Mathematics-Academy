import assert from "node:assert/strict";
import test, { after } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const state = { calls: [], curriculum: "caps", months: 4, amount: "3800.00", url: "https://sandbox.payfast.co.za/eng/process" };
const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)), configFile: false, appType: "custom",
  plugins: [{ name: "subscription-api-isolation", enforce: "pre", resolveId(id) {
    if (["server-only", "cloudflare:workers", "@/lib/auth", "@/lib/supabase/server", "@/lib/supabase/proxy"].includes(id)) return "\0subscription-stub:" + id;
    if (id.startsWith("@/lib/")) return fileURLToPath(new URL("../" + id.slice(2) + ".ts", import.meta.url));
  }, load(id) {
    if (id.endsWith("server-only")) return "export {};";
    if (id.endsWith("cloudflare:workers")) return 'export const env = { CMS_API_URL: "https://api.example.test/api/v1" };';
    if (id.endsWith("@/lib/auth")) return 'export async function requireVerifiedStudent() { return {id: "synthetic-student"}; }';
    if (id.endsWith("@/lib/supabase/server")) return 'export async function createSupabaseServerClient() {return {auth: {getSession: async()=>({data:{session:{access_token:"synthetic-token"}}})}};}';
    if (id.endsWith("@/lib/supabase/proxy")) return 'export async function refreshSupabaseSession() {return new Response(null);}';
  } }], server: { middlewareMode: true, hmr: false, ws: false },
});
after(() => vite.close());
const { subscriptionPlans, subscriptionCurricula, subscriptionPlan, subscriptionCurriculum, subscriptionPrice } = await vite.ssrLoadModule("/lib/subscription-plans.ts");
const api = await vite.ssrLoadModule("/lib/subscription-api.ts");
const { proxy } = await vite.ssrLoadModule("/proxy.ts");
test("private subscription checkout, status and invoices cannot be cached across students", async () => {
  for (const path of ["/subscriptions/4-months/checkout", "/subscriptions/8-months/checkout", "/subscriptions/status", "/api/subscriptions/SUB-ABC/invoice"]) {
    const response = await proxy({ nextUrl: new URL(path, "https://example.test") });
    assert.equal(response.headers.get("Cache-Control"), "private, no-store, max-age=0");
    assert.match(response.headers.get("Vary"), /Cookie/);
    assert.match(response.headers.get("Content-Security-Policy"), /form-action 'self' https:\/\/www.payfast.co.za https:\/\/sandbox.payfast.co.za/);
  }
});
test("two upfront plans have exact prices with the same five curriculum choices", () => {
  assert.deepEqual(subscriptionPlans.map(p => [p.months, p.price]), [[4,3800],[8,7600]]);
  assert.equal(subscriptionPrice(3800), "R3,800");
  assert.equal(subscriptionPrice(7600), "R7,600");
  assert.deepEqual(subscriptionCurricula.map(c=>c.value), ["caps","ieb","nated","ncv","university"]);
  assert.equal(subscriptionPlan("12-months"), undefined);
  assert.equal(subscriptionCurriculum(""), undefined);
  assert.equal(subscriptionCurriculum("all"), undefined);
});
test("checkout sends only term curriculum and stable idempotency key with a private bearer session", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    state.calls.push({url,init});
    return Response.json({subscription:{curriculum:state.curriculum,months:state.months,currency:"ZAR"},gateway_url:state.url,fields:{amount:state.amount}});
  };
  try {
    await api.createSubscriptionCheckout("caps",4);
    await api.createSubscriptionCheckout("caps",4);
    const first = state.calls[0];
    assert.equal(first.init.cache, "no-store");
    assert.equal(first.init.headers.Authorization, "Bearer synthetic-token");
    const body=JSON.parse(first.init.body);
    assert.deepEqual(Object.keys(body).sort(),["curriculum","idempotency_key","months"]);
    assert.equal(first.init.body,state.calls[1].init.body);
    state.amount="1.00";
    await assert.rejects(api.createSubscriptionCheckout("caps",4),/could not be verified/);
    state.amount="3800.00";state.url="https://attacker.example.test/eng/process";
    await assert.rejects(api.createSubscriptionCheckout("caps",4),/could not be verified/);
    await assert.rejects(api.getSubscription("../../other"),/Invalid subscription reference/);
  } finally { globalThis.fetch=original; }
});
