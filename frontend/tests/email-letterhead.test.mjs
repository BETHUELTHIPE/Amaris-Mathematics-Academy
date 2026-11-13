import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("account emails use company letterhead and retain their security variables and links", async () => {
  for (const [file, link, variables] of [
    ["confirm-signup.html", "{{ .ConfirmationURL }}", ["{{ .Token }}", "{{ .ConfirmationURL }}"]],
    ["magic-link-login.html", "{{ .ConfirmationURL }}", ["{{ .Token }}", "{{ .ConfirmationURL }}"]],
    ["recovery.html", "{{ .RedirectTo }}?token_hash={{ .TokenHash }}", ["{{ .Token }}", "{{ .RedirectTo }}", "{{ .TokenHash }}"]],
  ]) {
    const html = await readFile(new URL(`../email-templates/${file}`, import.meta.url), "utf8");
    assert.deepEqual(html.match(/{{.*?}}/g), variables, file);
    assert.ok(html.includes(`href="${link}"`), file);
    for (const text of ["Amaris Mathematics Academy logo", "Managing Director: Bethuel Moukangwe", "071 415 6665", "27 Tshivhase Street", "Official academy communication", "Professional mathematics education and learner support"]) assert.ok(html.includes(text), `${file}: ${text}`);
    assert.ok(!html.includes("{%"), "Hosted templates must not contain Django template syntax");
    assert.ok(!html.includes("cid:"), "Hosted Auth emails cannot rely on Django MIME attachments");
  }
});
