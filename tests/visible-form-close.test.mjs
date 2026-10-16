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

const accountBackDestinations = [
  ["app/register/page.tsx", "/"],
  ["app/login/page.tsx", "/"],
  ["app/forgot-password/page.tsx", "/login"],
  ["app/reset-password/page.tsx", "/forgot-password"],
  ["app/verify-email/page.tsx", "/register"],
];

for (const [file, destination] of accountBackDestinations) {
  test(`${file} provides a safe Back link inside its primary form beside Submit`, () => {
    const source = read(file);
    assert.match(source, /import \{ FormBackLink, FormCloseLink \} from "@\/components\/site\/form-close-link";/);
    const primaryForm = source.slice(source.indexOf("<form "), source.indexOf("</form>") + "</form>".length);
    assert.ok(primaryForm.includes(`<FormBackLink href="${destination}" />`), "Back should navigate to the correct in-site destination");
    assert.match(primaryForm, /<button type="submit"/, "keep the existing submit action");
    assert.ok(primaryForm.indexOf("<FormBackLink") < primaryForm.lastIndexOf('<button type="submit"'), "Back must appear in the form actions before Submit");
  });
}

test("Back and Close are safe keyboard-accessible links, never accidental form submissions", () => {
  const source = read("components/site/form-close-link.tsx");
  assert.match(source, /export function FormBackLink/);
  assert.match(source, /<ArrowLeft[^>]*aria-hidden="true"/);
  assert.match(source, /href=\{href\}/);
  assert.match(source, /min-h-11/);
  assert.match(source, /focus-visible:outline/);
  assert.doesNotMatch(source, /<button/);
});

test("course-search form offers a Close action while retaining GET search and Submit", () => {
  const source = read("app/courses/page.tsx");
  const form = source.slice(source.indexOf('<form method="get"'), source.indexOf("</form>") + "</form>".length);
  assert.match(form, /<FormCloseLink href="\/" \/>/);
  assert.match(form, /<button type="submit"/);
  assert.match(form, /name="q"/);
});

test("contact form retains its explicit Close action beside Submit", () => {
  const source = read("components/site/enquiry-form.tsx");
  assert.match(source, /<SubmitButton\s*\/>(\s*)<FormCloseLink\s*\/>/);
});
