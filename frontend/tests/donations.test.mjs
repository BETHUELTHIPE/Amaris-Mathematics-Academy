import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read=(path)=>readFileSync(new URL("../"+path,import.meta.url),"utf8");

test("support page includes donation checkout without storing card data",()=>{
  const page=read("app/support-our-project/page.tsx");
  assert.match(page,/DonationCheckoutForm/);
  assert.match(page,/not advertised as tax deductible/);
  const form=read("components/site/donation-checkout-form.tsx");
  assert.match(form,/Continue securely to PayFast/);
  assert.match(form,/consent/);
  assert.match(form,/availability==="disabled"/);
  assert.doesNotMatch(form,/card_number|cvv|expiry_date|credit_card_number/i);
});

test("donation route rejects cross-origin checkout and only allows known PayFast hosts",()=>{
  const route=read("app/api/donations/checkout/route.ts");
  assert.match(route,/sameOrigin\(request\)/);
  assert.match(route,/sandbox\.payfast\.co\.za/);
  assert.match(route,/www\.payfast\.co\.za/);
  assert.match(route,/no-store/);
});

test("status page never marks payment successful from browser redirect alone",()=>{
  const confirmation=read("components/site/donation-confirmation.tsx");
  assert.match(confirmation,/server-verified notification/);
  assert.match(confirmation,/api\/donations\//);
  assert.doesNotMatch(confirmation,/setStatus\(\{.*paid/);
});
