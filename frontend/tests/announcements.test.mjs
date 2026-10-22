import assert from "node:assert/strict";
import test from "node:test";
import { announcementDeadline, filterAnnouncements, prepareAnnouncements, safeAnnouncementLink, safeCmsMediaUrl } from "../lib/announcements.ts";

const now = Date.parse("2026-10-15T10:00:00Z");
const notice = (fields = {}) => ({ id: 1, title: "Class timetable", message: "Choose your Mathematics topic.", priority: 0, expires_at: null, link_label: "View classes", link_url: "/book-online-live-class", ...fields });

test("distinguishes an unavailable CMS from a published empty feed", () => {
  assert.equal(prepareAnnouncements(null, now), null);
  assert.equal(prepareAnnouncements({ results: [] }, now), null);
  assert.deepEqual(prepareAnnouncements([], now), []);
});

test("removes malformed and expired notices, including the exact expiry boundary", () => {
  const current = notice({ id: 3, expires_at: "2026-10-15T10:01:00Z" });
  assert.deepEqual(prepareAnnouncements([
    null, { title: "Incomplete" }, notice({ priority: "high" }),
    notice({ expires_at: "invalid" }), notice({ expires_at: "2026-10-15T10:00:00Z" }), current,
  ], now), [current]);
});

test("prioritizes important notices before newest general notices", () => {
  assert.deepEqual(prepareAnnouncements([notice({ id: 4 }), notice({ id: 2, priority: 5 }), notice({ id: 5 })], now).map((item) => item.id), [2, 5, 4]);
});

test("search and priority filters combine without changing the feed", () => {
  const items = [notice({ id: 1, priority: 2 }), notice({ id: 2, message: "Account support" })];
  assert.deepEqual(filterAnnouncements(items, "  MATHEMATICS  ", true).map((item) => item.id), [1]);
  assert.deepEqual(filterAnnouncements(items, "support", true), []);
  assert.equal(filterAnnouncements(items, "support", false).length, 1);
  assert.equal(items.length, 2);
});

test("notice links reject executable, credentialed and browser-normalized destinations", () => {
  for (const value of ["javascript:alert(1)", "data:text/html,hello", "//evil.example", "/\\evil.example", "https://user:secret@example.com", "http://example.com", "relative/path"]) {
    assert.equal(safeAnnouncementLink(value), null, value);
  }
  assert.equal(safeAnnouncementLink("https://example.com/a\nb"), null);
  assert.equal(safeAnnouncementLink(" /courses?level=12#details "), "/courses?level=12#details");
  assert.equal(safeAnnouncementLink("https://example.com/notice"), "https://example.com/notice");
});

test("expiry display uses South African time independently of server timezone", () => {
  const result = announcementDeadline("2026-10-15T10:00:00Z");
  assert.match(result, /15/);
  assert.match(result, /12:00/);
  assert.equal(announcementDeadline(null), null);
  assert.equal(announcementDeadline("invalid"), null);
});

test("marketing media URL must stay on the trusted CMS API origin", () => {
  const base = "https://amaris-production-web.onrender.com/api/v1";
  const good = "https://amaris-production-web.onrender.com/api/v1/marketing-media/12/";
  assert.equal(safeCmsMediaUrl(good, base), good);
  for (const value of [
    "https://evil.example/api/v1/marketing-media/12/",
    "//evil.example/api/v1/marketing-media/12/",
    "http://amaris-production-web.onrender.com/api/v1/marketing-media/12/",
    "https://amaris-production-web.onrender.com/api/v1/marketing-media/12/?X-Amz-Signature=secret",
    "javascript:alert(1)",
    "/api/v1/student/payments/12/",
  ]) {
    assert.equal(safeCmsMediaUrl(value, base), null, value);
  }
});

test("validates optional image/video/PDF media metadata and retains legacy notice shape", () => {
  const valid = { id: 4, title: "Matric briefing", kind: "video", order: 0, download_url: "https://example.com" };
  const [result] = prepareAnnouncements([notice({ media: [valid, { ...valid, id: "bad" }] })], now);
  assert.deepEqual(result.media, [valid]);
  assert.equal("media" in prepareAnnouncements([notice()], now)[0], false);
});
