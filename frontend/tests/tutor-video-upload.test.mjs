import test from "node:test";
import assert from "node:assert/strict";
import { MAX_TUTOR_VIDEO_BYTES, tutorVideoRequestError } from "../lib/tutor-video-request.mjs";

const request = (headers = {}) => ({ url: "https://academy.example.test/api/tutor/videos", headers: new Headers({ origin: "https://academy.example.test", "content-type": "multipart/form-data; boundary=synthetic", ...headers }) });
test("same-origin multipart submission can stream without a content-length header", () => {
  assert.equal(tutorVideoRequestError(request()), null);
});
test("cross-origin or absent origin cannot use the signed-in tutor session", () => {
  assert.equal(tutorVideoRequestError(request({ origin: "https://attacker.example.test" })).status, 403);
  const missing = request(); missing.headers.delete("origin");
  assert.equal(tutorVideoRequestError(missing).status, 403);
  assert.equal(tutorVideoRequestError(request({ "sec-fetch-site": "cross-site" })).status, 403);
});
test("wrong encoding and oversized or invalid declared lengths fail before forwarding", () => {
  assert.equal(tutorVideoRequestError(request({ "content-type": "application/json" })).status, 415);
  assert.equal(tutorVideoRequestError(request({ "content-length": String(MAX_TUTOR_VIDEO_BYTES + 65537) })).status, 413);
  assert.equal(tutorVideoRequestError(request({ "content-length": "-1" })).status, 413);
});
