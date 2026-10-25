import assert from "node:assert/strict";
import test from "node:test";
import { announcementYouTube } from "../lib/announcement-youtube.ts";

const id = "M7lc1UVf-VE";
const playlist = "PLU1CWISq1SWo";

test("videos use a rebuilt privacy-enhanced embed and a public fallback", () => {
  for (const url of [
    `https://youtu.be/${id}?si=tracking`, `https://www.youtube.com/watch?v=${id}&autoplay=1`,
    `https://www.youtube.com/shorts/${id}`, `https://www.youtube.com/live/${id}`,
    `https://www.youtube-nocookie.com/embed/${id}`, `https://studio.youtube.com/video/${id}/edit`,
  ]) {
    assert.deepEqual(announcementYouTube(url), {
      kind: "video", watchUrl: `https://www.youtube.com/watch?v=${id}`,
      embedUrl: `https://www.youtube-nocookie.com/embed/${id}?playsinline=1`,
    });
  }
});

test("the supplied Studio playlist URL never becomes an iframe or visitor destination", () => {
  for (const url of [`https://studio.youtube.com/playlist/${playlist}/videos`,
    `https://www.youtube.com/playlist?list=${playlist}`, `https://www.youtube-nocookie.com/embed/videoseries?list=${playlist}`]) {
    const parsed = announcementYouTube(url);
    assert.equal(parsed.kind, "playlist");
    assert.equal(parsed.watchUrl, `https://www.youtube.com/playlist?list=${playlist}`);
    assert.equal(parsed.embedUrl, `https://www.youtube-nocookie.com/embed/videoseries?list=${playlist}&playsinline=1`);
  }
});

test("host spoofing, executable URLs and malformed CMS metadata cannot create embeds", () => {
  for (const url of [undefined, null, {}, 42, "", "javascript:alert(1)", `http://youtu.be/${id}`,
    `https://youtube.com.attacker.test/watch?v=${id}`, `https://youtube.com@attacker.test/watch?v=${id}`,
    `https://user:password@youtube.com/watch?v=${id}`, `https://youtube.com\\@attacker.test/watch?v=${id}`,
    `https://www.youtube.com/watch?v=${id}\n&x=1`, "https://www.youtube.com/watch?v=invalid",
    "https://www.youtube.com/playlist?list=%3Cscript%3E", "https://studio.youtube.com/"]) {
    assert.equal(announcementYouTube(url), null, String(url));
  }
});
