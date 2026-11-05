import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_VIDEO_DOCUMENT_BYTES, MAX_VIDEO_UPLOAD_BODY_BYTES,
  validateVideoDocuments, boundedVideoUpload,
} from "../lib/video-document-limits.mjs";

const pdf = size => ({ size, type: "application/pdf" });

test("accepts 1 GB exactly, with a combined quota and at most five private documents", () => {
  assert.equal(validateVideoDocuments([pdf(MAX_VIDEO_DOCUMENT_BYTES)]), "");
  assert.equal(validateVideoDocuments([pdf(MAX_VIDEO_DOCUMENT_BYTES / 2), pdf(MAX_VIDEO_DOCUMENT_BYTES / 2)]), "");
  assert.match(validateVideoDocuments([pdf(MAX_VIDEO_DOCUMENT_BYTES + 1)]), /no larger than 1 GB/);
  assert.match(validateVideoDocuments([pdf(MAX_VIDEO_DOCUMENT_BYTES), pdf(1)]), /total no more than 1 GB/);
  assert.match(validateVideoDocuments(Array.from({ length: 6 }, () => pdf(1))), /five/);
  assert.match(validateVideoDocuments([pdf(0)]), /non-empty/);
  assert.match(validateVideoDocuments([{ size: 1, type: "text/html" }]), /PDF, JPEG or PNG/);
  assert.equal(validateVideoDocuments([]), "");
});

function byteStream(total) {
  const chunk = new Uint8Array(1024 * 1024);
  return new ReadableStream({
    pull(controller) {
      if (!total) return controller.close();
      const size = Math.min(total, chunk.length);
      total -= size;
      controller.enqueue(chunk.subarray(0, size));
    },
  });
}

async function consume(body) {
  let bytes = 0;
  for await (const chunk of body) bytes += chunk.byteLength;
  return bytes;
}

test("streams 1 GB plus multipart overhead with bounded chunks", async () => {
  const state = boundedVideoUpload(byteStream(MAX_VIDEO_UPLOAD_BODY_BYTES));
  assert.equal(await consume(state.body), MAX_VIDEO_UPLOAD_BODY_BYTES);
  assert.equal(state.exceeded, false);
});

test("rejects an over-limit chunked upload even without Content-Length", async () => {
  const state = boundedVideoUpload(byteStream(MAX_VIDEO_UPLOAD_BODY_BYTES + 1));
  await assert.rejects(consume(state.body), /no more than 1 GB/);
  assert.equal(state.exceeded, true);
});

test("forwards the original multipart bytes without rewriting their boundary", async () => {
  const original = new TextEncoder().encode("--boundary\r\nprivate-document\r\n--boundary--\r\n");
  const state = boundedVideoUpload(new ReadableStream({
    start(controller) { controller.enqueue(original); controller.close(); },
  }));
  assert.deepEqual(new Uint8Array(await new Response(state.body).arrayBuffer()), original);
});
