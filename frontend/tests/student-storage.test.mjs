import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const storagePath = fileURLToPath(new URL("../lib/student-storage.ts", import.meta.url));
const pagePath = fileURLToPath(new URL("../app/documents/page.tsx", import.meta.url));
const routePath = fileURLToPath(new URL("../app/documents/file/route.ts", import.meta.url));

const [storageSource, pageSource, routeSource] = await Promise.all([
  readFile(storagePath, "utf8"),
  readFile(pagePath, "utf8"),
  readFile(routePath, "utf8"),
]);

test("student files use the private Amaris Supabase bucket and user UUID prefix", () => {
  assert.match(storageSource, /STUDENT_STORAGE_BUCKET = "Amaris Mathematics Academy"/);
  assert.match(storageSource, /\$\{student\.id\}\/\$\{category\}\//);
  assert.match(storageSource, /createSignedUrl\(path, expiresInSeconds/);
  assert.match(storageSource, /path\.startsWith\(prefix\)/);
});

test("student documents page supports secure upload and signed download", () => {
  assert.match(pageSource, /uploadStudentDocumentAction/);
  assert.match(pageSource, /Private Supabase Storage/);
  assert.match(pageSource, /\/documents\/file\?path=/);
  assert.match(routeSource, /createStudentFileSignedUrl/);
});

test("student storage enforces the configured 50 MB application limit", () => {
  assert.match(storageSource, /50 \* 1024 \* 1024/);
  assert.match(storageSource, /file\.size > STUDENT_STORAGE_MAX_BYTES/);
});
