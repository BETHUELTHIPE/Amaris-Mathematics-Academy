import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { registerHooks } from "node:module";
import test from "node:test";

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "cloudflare:workers") {
      return { shortCircuit: true, url: "data:text/javascript,export const env = {};" };
    }
    return nextResolve(specifier, context);
  },
});

const page = await readFile(new URL("../app/request-a-video/page.tsx", import.meta.url), "utf8");
const form = await readFile(
  new URL("../components/site/video-request-form.tsx", import.meta.url),
  "utf8",
);
const confirmation = await readFile(
  new URL("../app/request-a-video/confirmation/page.tsx", import.meta.url),
  "utf8",
);
const proxy = await readFile(
  new URL("../app/api/video-requests/checkout/route.ts", import.meta.url),
  "utf8",
);
const dashboard = await readFile(new URL("../app/dashboard/page.tsx", import.meta.url), "utf8");

test("request-a-video page requires a verified student and explains the paid queue", () => {
  assert.match(page, /requireVerifiedStudent\("\/request-a-video"\)/);
  assert.match(page, /Payment is verified before your permanent ticket enters the tutor queue/);
  assert.match(page, /Supporting documents are stored in the private student bucket/);
});

test("request form supports all programmes, secure files and server-priced checkout", () => {
  for (const label of ["CAPS", "IEB", "TVET", "University"]) assert.match(form, new RegExp(label));
  assert.match(form, /application\/pdf,image\/jpeg,image\/png/);
  assert.match(form, /Up to 1 GB per file and 1 GB total/);
  assert.match(form, /data\.delete\("documents"\)/);
  assert.match(form, /uploadStudentDocument/);
  assert.match(form, /\/api\/video-requests\/upload-session/);
  assert.match(form, /\/api\/video-requests\/documents/);
  assert.doesNotMatch(form, /data\.append\("documents"/);
  assert.match(form, /Server-priced/);
  assert.match(form, /Continue to PayFast/);
  assert.doesNotMatch(form, /localStorage|sessionStorage/);
});

test("checkout proxy forwards the authenticated multipart request without exposing credentials", () => {
  assert.match(proxy, /createStudentVideoRequestCheckout/);
  assert.match(proxy, /request\.formData\(\)/);
  assert.match(proxy, /await getStudentIdentity\(\)/);
  assert.match(proxy, /status: student \? 403 : 401/);
  assert.match(proxy, /Cross-site video requests are not allowed/);
  assert.doesNotMatch(proxy, /SUPABASE_SERVICE_ROLE|PAYFAST_MERCHANT_KEY|PAYFAST_PASSPHRASE/);
});

test("large documents use resumable Supabase transfer and verified ownership", async () => {
  const signer = await readFile(new URL("../app/api/video-requests/upload-session/route.ts", import.meta.url), "utf8");
  const completed = await readFile(new URL("../app/api/video-requests/documents/route.ts", import.meta.url), "utf8");
  const uploader = await readFile(new URL("../lib/supabase/resumable-upload.ts", import.meta.url), "utf8");
  const backend = await readFile(new URL("../../backend/content/services/video_requests.py", import.meta.url), "utf8");
  assert.match(signer, /await getStudentIdentity\(\)/);
  assert.match(signer, /getStudentVideoRequest\(reference\)/);
  assert.match(signer, /createSignedUploadUrl\(path\)/);
  assert.match(signer, /videoRequest\.status !== "pending_payment"/);
  assert.match(signer, /document_total_bytes \+ fileSize > ONE_GIB/);
  assert.match(signer, /Cache-Control.*private, no-store/);
  assert.match(completed, /registerStudentVideoDocument/);
  assert.match(uploader, /CHUNK_BYTES = 6 \* 1024 \* 1024/);
  assert.match(uploader, /"x-signature"/);
  assert.match(uploader, /"PATCH"/);
  assert.match(uploader, /"HEAD"/);
  assert.doesNotMatch(uploader, /localStorage|sessionStorage|SUPABASE_SERVICE_ROLE/);
  assert.match(backend, /def register_resumable_document/);
  assert.match(backend, /VideoRequest\.Status\.PENDING_PAYMENT/);
  assert.match(backend, /store\.size\(storage_path\)/);
  assert.match(backend, /MAX_RESUMABLE_DOCUMENT_SIZE = 1024 \* 1024 \* 1024/);
});

test("completed videos are only rendered from authenticated status data", () => {
  assert.match(confirmation, /requireVerifiedStudent/);
  assert.match(confirmation, /item\?\.status === "ready" && item\.video/);
  assert.match(confirmation, /youtube-nocookie\.com\/embed/);
  assert.match(confirmation, /controlsList="nodownload"/);
  assert.match(dashboard, /getStudentVideoRequests/);
  assert.match(dashboard, /My requested videos/);
});

test("video checkout security headers permit PayFast and embedded lessons while keeping responses private", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("video-security-test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("https://example.test/api/video-requests/checkout", {
      method: "POST",
      headers: { "cf-connecting-ip": "203.0.113.11" },
    }),
    { CHECKOUT_RATE_LIMITER: { limit: async () => ({ success: false }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("cache-control"), "private, no-store, max-age=0");
  assert.match(response.headers.get("vary") ?? "", /Cookie/i);
  const policy = response.headers.get("content-security-policy") ?? "";
  assert.match(policy, /form-action 'self' https:\/\/www\.payfast\.co\.za https:\/\/sandbox\.payfast\.co\.za;/);
  assert.match(policy, /frame-src 'self' https:\/\/www\.youtube-nocookie\.com;/);
  assert.match(policy, /frame-ancestors 'none'/);
  assert.match(policy, /object-src 'none'/);
});

