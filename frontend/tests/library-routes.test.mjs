import assert from "node:assert/strict";
import test, { after, beforeEach } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const root = fileURLToPath(new URL("..", import.meta.url));
const originalFetch = globalThis.fetch;
const state = globalThis.__libraryTest = {};
const vite = await createServer({
  root, configFile: false, appType: "custom", esbuild: { jsx: "automatic" }, ssr: { noExternal: ["next"] }, resolve: { alias: { "@": root } },
  server: { middlewareMode: true, hmr: false, ws: false },
  plugins: [{
    name: "library-isolated-auth",
    enforce: "pre",
    resolveId(id) {
      if (["server-only", "cloudflare:workers", "next/server", "next/navigation", "next/link"].includes(id) || id.endsWith("/lib/supabase/server") || id === "@/lib/supabase/server") return `\0library-mock:${id}`;
    },
    load(id) {
      if (!id.startsWith("\0library-mock:")) return;
      if (id.endsWith("server-only")) return "export {};";
      if (id.endsWith("cloudflare:workers")) return 'export const env = { CMS_API_URL: "https://cms.example.test/api/v1" };';
      if (id.endsWith("next/navigation")) return 'export const useRouter = () => ({ refresh() {} });';
      if (id.endsWith("next/link")) return 'import { createElement } from "react"; export default function Link({ children, ...props }) { return createElement("a", props, children); }';
      if (id.endsWith("next/server")) return `export class NextResponse extends Response { static json(value, init = {}) { return new NextResponse(JSON.stringify(value), { ...init, headers: { ...init.headers, "content-type": "application/json" } }); } }`;
      return `export async function createSupabaseServerClient() { return { auth: {
        getUser: async () => ({ data: { user: globalThis.__libraryTest.user }, error: null }),
        getSession: async () => ({ data: { session: { access_token: "synthetic-verified-token" } }, error: null })
      } }; }`;
    },
  }],
});
const upload = await vite.ssrLoadModule("/app/api/library/upload/route.ts");
const publication = await vite.ssrLoadModule("/app/api/library/[id]/route.ts");
const download = await vite.ssrLoadModule("/app/api/library/[id]/download/route.ts");
const { boundedBody } = await vite.ssrLoadModule("/lib/library-http.ts");
const { LibraryShelf } = await vite.ssrLoadModule("/components/library/library-shelf.tsx");
const { LibraryUpload } = await vite.ssrLoadModule("/components/library/library-controls.tsx");
const id = "b692f777-c486-4543-8d31-0d9b693e1e4a";
const context = { params: Promise.resolve({ id }) };
const origin = "https://academy.example.test";
function form() {
  const data = new FormData();
  for (const [key, value] of Object.entries({ title: "Algebra", subject: "Mathematics", level: "Grade 12", resource_type: "worksheet", sharing_permitted: "true", is_published: "true" })) data.set(key, value);
  data.set("file", new File(["%PDF-1.7\nSynthetic"], "algebra.pdf", { type: "application/pdf" }));
  return data;
}
beforeEach(() => {
  state.user = { email_confirmed_at: "2026-10-31", id: "synthetic-user" };
  state.calls = [];
  state.respond = () => Response.json({ results: [], count: 0, page: 1, page_size: 24 });
  globalThis.fetch = async (url, init) => { state.calls.push({ url: String(url), init }); return state.respond(String(url), init); };
});
after(async () => { globalThis.fetch = originalFetch; delete globalThis.__libraryTest; await vite.close(); });

test("anonymous and unverified download requests stop before reaching Django", async () => {
  for (const user of [null, { email_confirmed_at: null }]) {
    state.user = user;
    const response = await download.GET(new Request(`${origin}/api/library/${id}/download`), context);
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("cache-control"), "private, no-store");
  }
  assert.equal(state.calls.length, 0);
});

test("upload and publication reject foreign origins before authentication or API calls", async () => {
  const response = await upload.POST(new Request(`${origin}/api/library/upload`, { method: "POST", headers: { Origin: "https://foreign.example.test" }, body: form() }));
  assert.equal(response.status, 403);
  const patch = await publication.PATCH(new Request(`${origin}/api/library/${id}`, { method: "PATCH", body: '{}' }), context);
  assert.equal(patch.status, 403);
  assert.equal(state.calls.length, 0);
});

test("a student cannot buffer or forward an upload without Django tutor approval", async () => {
  state.respond = () => Response.json({ detail: "Tutor access denied" }, { status: 401 });
  const response = await upload.POST(new Request(`${origin}/api/library/upload`, { method: "POST", headers: { Origin: origin }, body: form() }));
  assert.equal(response.status, 401);
  assert.equal(state.calls.length, 1);
  assert.match(state.calls[0].url, /\/tutor\/library\/$/);
  assert.equal(state.calls[0].init.body, undefined);
});

test("approved tutor upload forwards the document with only a server-derived token", async () => {
  state.respond = (_url, init) => init.method === "POST" ? Response.json({ id, title: "Algebra" }, { status: 201 }) : Response.json({ results: [] });
  const response = await upload.POST(new Request(`${origin}/api/library/upload`, { method: "POST", headers: { Origin: origin }, body: form() }));
  assert.equal(response.status, 201);
  const { init } = state.calls[1];
  assert.equal(init.headers.Authorization, "Bearer synthetic-verified-token");
  assert.equal(init.headers["Content-Type"], undefined, "fetch must supply the multipart boundary");
  assert.equal(init.body.get("file").name, "algebra.pdf");
  assert.equal(init.body.get("file").size, 18);
  assert.equal(init.cache, "no-store");
  assert.equal(response.headers.get("cache-control"), "private, no-store");
});

test("body size limit covers both a declared length and a streamed request", async () => {
  const body = new Request(`${origin}/upload`, { method: "POST", headers: { "Content-Length": "100" }, body: "abc" });
  await assert.rejects(boundedBody(body, 10), error => error.status === 413);
  const streamed = new Request(`${origin}/upload`, { method: "POST", body: "x".repeat(100) });
  await assert.rejects(boundedBody(streamed, 10), error => error.status === 413);
});

test("publication update cannot forward ownership or arbitrary metadata", async () => {
  const response = await publication.PATCH(new Request(`${origin}/api/library/${id}`, {
    method: "PATCH", headers: { Origin: origin }, body: JSON.stringify({ is_published: false, uploaded_by: 999, title: "spoof" }),
  }), context);
  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(state.calls[0].init.body), { is_published: false });
  assert.match(state.calls[0].url, /\/tutor\/library\//);
});

test("student download redirects to the private signed URL without forwarding the token", async () => {
  state.respond = () => new Response(null, { status: 302, headers: { Location: "https://storage.example.test/file?signature=synthetic" } });
  const response = await download.GET(new Request(`${origin}/api/library/${id}/download`), context);
  assert.equal(response.status, 302);
  assert.match(response.headers.get("location"), /signature=synthetic/);
  assert.equal(response.headers.get("authorization"), null);
  assert.equal(state.calls.length, 1, "the server must not follow the signed redirect");
  assert.match(state.calls[0].url, /\/student\/library\//);
  assert.equal(state.calls[0].init.redirect, "manual");
});

test("local downloads stream exact contents and hidden documents return 404", async () => {
  state.respond = () => new Response("synthetic worksheet", { headers: { "Content-Type": "text/plain", "Content-Disposition": 'attachment; filename="worksheet.txt"' } });
  const response = await download.GET(new Request(`${origin}/api/library/${id}/download?role=tutor`), context);
  assert.equal(await response.text(), "synthetic worksheet");
  assert.equal(response.headers.get("content-disposition"), 'attachment; filename="worksheet.txt"');
  assert.match(state.calls[0].url, /\/tutor\/library\//);
  state.respond = () => Response.json({ detail: "Not found" }, { status: 404 });
  assert.equal((await download.GET(new Request(`${origin}/api/library/${id}/download`), context)).status, 404);
});

test("invalid IDs and unsafe download locations are rejected", async () => {
  const bad = { params: Promise.resolve({ id: "../private" }) };
  assert.equal((await download.GET(new Request(`${origin}/download`), bad)).status, 400);
  assert.equal(state.calls.length, 0);
  state.respond = () => new Response(null, { status: 302, headers: { Location: "http://storage.example.test/file" } });
  assert.equal((await download.GET(new Request(`${origin}/download`), context)).status, 503);
});


test("Library cards render escaped metadata, role-specific downloads and tutor-owned controls", () => {
  const resource = { id, title: "Algebra <ScRiPt>alert(1)</ScRiPt>", description: "Practice", resource_type: "worksheet", subject: "Mathematics", level: "Grade 12", original_name: "worksheet.pdf", size_bytes: 1024, is_published: true, can_manage: true };
  const data = { results: [resource], count: 25, page: 1, page_size: 24 };
  const student = renderToStaticMarkup(createElement(LibraryShelf, { data, role: "student", query: { q: "a & b" } }));
  assert.match(student, /&lt;ScRiPt&gt;/);
  assert.doesNotMatch(student, /<script>/i);
  assert.match(student, new RegExp(`/api/library/${id}/download\\?role=student`));
  assert.doesNotMatch(student, /Hide from students/);
  assert.match(student, /page=2/);
  const tutor = renderToStaticMarkup(createElement(LibraryShelf, { data, role: "tutor", query: {} }));
  assert.match(tutor, /role=tutor/);
  assert.match(tutor, /Hide from students/);
});

test("upload form renders labeled file input, sharing permission and required teaching metadata", () => {
  const html = renderToStaticMarkup(createElement(LibraryUpload));
  for (const name of ["title", "resource_type", "subject", "level", "file", "sharing_permitted"]) assert.ok(html.includes(`name="${name}"`));
  assert.match(html, /accept=".pdf,.docx,.xlsx,.pptx,.txt"/);
  assert.match(html, /Maximum 50 MB/);
  assert.match(html, /Upload to Library/);
  assert.match(html, /<summary/);
});
