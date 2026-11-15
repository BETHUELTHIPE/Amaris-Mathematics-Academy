import assert from "node:assert/strict";
import test from "node:test";
import { personnelRequestError, readPersonnelJSON } from "../lib/tutor-personnel-request.mjs";

const request = (headers = {}, body = "{}") => new Request("https://academy.example/api/tutor/contracts", {
  method: "POST", headers: { origin: "https://academy.example", "content-type": "application/json", ...headers }, body,
});

test("employment contract accepts only bounded same-origin JSON", async () => {
  assert.equal(personnelRequestError(request()), null);
  assert.equal(personnelRequestError(request({ origin: "https://attacker.example" })).status, 403);
  assert.equal(personnelRequestError(request({ "content-type": "text/plain" })).status, 415);
  assert.equal(personnelRequestError(request({ "content-length": "65537" })).status, 413);
  assert.deepEqual(await readPersonnelJSON(request({}, '{"signature_name":"Tutor Example"}')), { signature_name: "Tutor Example" });
  await assert.rejects(readPersonnelJSON(request({}, JSON.stringify({ address: "x".repeat(65536) }))));
});
