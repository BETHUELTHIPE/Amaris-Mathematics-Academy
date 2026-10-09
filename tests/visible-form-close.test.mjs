import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const read = (file) => fs.readFileSync(path.join(process.cwd(), file), "utf8");

const standaloneForms = [
  "app/register/page.tsx",
  "app/login/page.tsx",
  "app/forgot-password/page.tsx",
  "app/reset-password/page.tsx",
  "app/verify-email/page.tsx",
  "app/contact/page.tsx",
];

for (const file of standaloneForms) {
  test(`${file} has a visible, shared Close control before its form`, () => {
    const source = read(file);
    assert.match(source, /import \{ FormCloseLink \} from "@\/components\/site\/form-close-link";/);
    const closeIndex = source.indexOf("<FormCloseLink");
    const formIndex = source.includes("<EnquiryForm") ? source.indexOf("<EnquiryForm") : source.indexOf("<form ");
    assert.ok(closeIndex >= 0 && formIndex > closeIndex, "Close should be visible before the form");
  });
}

test("standalone Close is a navigational link, not a form submit button", () => {
  const source = read("components/site/form-close-link.tsx");
  assert.match(source, /<Link\s/);
  assert.match(source, /aria-label="Close form"/);
  assert.match(source, />\s*Close\s*<\/Link>/);
  assert.doesNotMatch(source, /type="submit"/);
  assert.match(source, /focus-visible:outline/);
});

for (const [file, primitive] of [
  ["components/ui/dialog.tsx", "DialogPrimitive"],
  ["components/ui/sheet.tsx", "SheetPrimitive"],
  ["components/ui/drawer.tsx", "DrawerPrimitive"],
]) {
  test(`${file} has a visible focusable Close action`, () => {
    const source = read(file);
    assert.match(source, new RegExp(`<${primitive}\\.Close`));
    assert.match(source, /<XIcon[^>]*aria-hidden="true"[^>]*\/>\s*Close/);
    assert.match(source, /focus-visible:outline/);
  });
}

test("contact enquiry offers a Close action beside submit and retains confirmation Close", () => {
  const source = read("components/site/enquiry-form.tsx");
  assert.match(source, /<SubmitButton\s*\/>\s*<FormCloseLink\s*\/>/);
  assert.match(source, /Close enquiry confirmation and return to contact form/);
});
