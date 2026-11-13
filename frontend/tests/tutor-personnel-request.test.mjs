import assert from "node:assert/strict";
import test from "node:test";
import { personnelRequestError, readPersonnelJSON } from "../lib/tutor-personnel-request.mjs";

const request = (headers = {}, body = "{}") => new Request("https://academy.example/api/tutor/forms", {
  method: "POST", headers: { origin: "https://academy.example", "content-type": "application/json", ...headers }, body,
});
test("personnel form permits only same-origin JSON and rejects declared oversize", () => {
  assert.equal(personnelRequestError(request()), null);
  assert.equal(personnelRequestError(request({ origin: "https://attacker.example" })).status, 403);
  assert.equal(personnelRequestError(request({ "sec-fetch-site": "cross-site" })).status, 403);
  assert.equal(personnelRequestError(request({ "content-type": "text/plain" })).status, 415);
  assert.equal(personnelRequestError(request({ "content-length": "65537" })).status, 413);
  const missingOrigin = request(); missingOrigin.headers.delete("origin");
  assert.equal(personnelRequestError(missingOrigin).status, 403);
});
test("personnel JSON reader bounds actual bytes without relying on content length", async () => {
  assert.deepEqual(await readPersonnelJSON(request({}, '{"kind":"leave"}')), { kind: "leave" });
  await assert.rejects(readPersonnelJSON(request({}, "{")));
  await assert.rejects(readPersonnelJSON(request({}, "[]")));
  await assert.rejects(readPersonnelJSON(request({}, '"string"')));
  await assert.rejects(readPersonnelJSON(request({}, JSON.stringify({ reason: "x".repeat(65536) }))));
});
