import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const wizard = fs.readFileSync(
  new URL("../app/request-your-own-video/page.tsx", import.meta.url),
  "utf8",
);
const checkout = fs.readFileSync(
  new URL("../app/request-your-own-video/checkout/page.tsx", import.meta.url),
  "utf8",
);
const confirmation = fs.readFileSync(
  new URL("../app/request-your-own-video/confirmation/page.tsx", import.meta.url),
  "utf8",
);
const studentApi = fs.readFileSync(
  new URL("../lib/student-api.ts", import.meta.url),
  "utf8",
);
const cms = fs.readFileSync(new URL("../lib/cms.ts", import.meta.url), "utf8");
const options = fs.readFileSync(
  new URL("../lib/video-requests.ts", import.meta.url),
  "utf8",
);

test("custom video request is surfaced in header navigation", () => {
  assert.match(cms, /Request Your Own Video/);
  assert.match(cms, /\/request-your-own-video/);
});

test("wizard uses supported curriculum and subject taxonomy", () => {
  for (const label of ["CAPS", "IEB", "TVET", "University"]) {
    assert.match(options, new RegExp(label));
  }
  assert.match(options, /Mathematics/);
  assert.match(options, /Mathematical Literacy/);
  assert.match(wizard, /Grade \/ level/);
});

test("wizard does not invent a custom video price or curriculum topic list", () => {
  assert.match(options, /price: null/);
  assert.match(options, /caps_mathematics_topics: \[\]/);
  assert.match(wizard, /No price has been invented or hardcoded/);
  assert.doesNotMatch(wizard, /R250|R399/);
  assert.doesNotMatch(checkout, /R250|R399/);
});

test("supporting upload accepts multiple common document formats", () => {
  assert.match(wizard, /name="files"/);
  assert.match(wizard, /multiple/);
  for (const extension of [".pdf", ".jpg", ".png", ".heic", ".docx"]) {
    assert.match(wizard, new RegExp(extension.replace(".", "\\.")));
  }
});

test("student API preserves multipart bodies without forcing JSON content type", () => {
  assert.match(studentApi, /init\.body instanceof FormData/);
  assert.match(studentApi, /createStudentCustomVideoRequest/);
  assert.match(studentApi, /\/student\/custom-videos\//);
});

test("checkout uses server amount and PayFast verification language", () => {
  assert.match(checkout, /checkout\.amount/);
  assert.match(checkout, /administrator-configured server price/);
  assert.match(checkout, /server verifies the PayFast notification/);
});

test("confirmation tells the student that invoice and team notification are queued", () => {
  assert.match(confirmation, /invoice PDF/);
  assert.match(confirmation, /academy team is notified/);
});
