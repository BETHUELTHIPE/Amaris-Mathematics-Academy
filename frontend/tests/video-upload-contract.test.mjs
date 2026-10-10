import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const form = readFileSync(new URL("../components/site/video-request-form.tsx", import.meta.url), "utf8");
const helper = readFileSync(new URL("../lib/video-upload.ts", import.meta.url), "utf8");
const proxy = readFileSync(new URL("../app/api/video-requests/uploads/[reference]/route.ts", import.meta.url), "utf8");

test("topic request supports folder selection and progress without proxying file bytes", () => {
  assert.match(form, /webkitdirectory/);
  assert.match(form, /name="documents"/);
  assert.match(form, /name="folder"/);
  assert.match(form, /uploadVideoRequestFiles/);
  assert.match(form, /role="status"/);
  assert.match(helper, /VIDEO_UPLOAD_LIMIT_BYTES = 1024 \* 1024 \* 1024/);
  assert.match(helper, /VIDEO_UPLOAD_MAX_FILES = 200/);
  assert.match(helper, /file\.slice\(start, end\)/);
  assert.match(helper, /method: "PUT"/);
  assert.match(helper, /response\.headers\.get\("ETag"\)/);
  assert.doesNotMatch(proxy, /request\.formData\(\)/);
});

test("upload control validates verified student session", () => {
  assert.match(proxy, /getStudentIdentity/);
  assert.match(proxy, /emailVerified/);
  assert.match(proxy, /Cross-site uploads are not allowed/);
});
