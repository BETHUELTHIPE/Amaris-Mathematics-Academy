import assert from "node:assert/strict";
import test from "node:test";
import { groupNavigation } from "../lib/navigation.ts";

const urls = ["/courses", "/how-it-works", "/pricing", "/matric-upgrades", "/about", "/announcements", "/request-a-video", "/book-online-live-class", "/tutor/apply", "/contact"];
const links = urls.map(url => ({ url, label: url, open_in_new_tab: false }));

test("grouping preserves every managed destination exactly once and features matric", () => {
  const { featured, groups } = groupNavigation(links);
  const result = [...featured, ...groups.flatMap(group => group.links)];
  assert.deepEqual(featured.map(link => link.url), ["/matric-upgrades"]);
  for (const url of urls) assert.equal(result.filter(link => link.url === url).length, 1, url);
  assert.deepEqual(groups.map(group => group.label), ["Learn", "Resources", "Academy"]);
  assert.ok(groups[0].links.some(link => link.url === "/book-online-live-class"));
  assert.ok(groups[2].links.some(link => link.url === "/tutor/login"));
});

test("custom CMS links retain labels and new-tab behaviour without being lost", () => {
  const custom = { url: "https://example.com/resource", label: "Study library", open_in_new_tab: true };
  const result = groupNavigation([...links, custom]).groups[1].links;
  assert.deepEqual(result.find(link => link.url === custom.url), { ...custom, description: "Explore more from Amaris" });
});

test("a managed tutor portal is not duplicated", () => {
  const managedPortal = { url: "/tutor/login", label: "Tutor workspace", open_in_new_tab: false };
  const result = groupNavigation([...links, managedPortal]).groups.flatMap(group => group.links);
  assert.equal(result.filter(link => link.url === managedPortal.url).length, 1);
  assert.equal(result.find(link => link.url === managedPortal.url).label, managedPortal.label);
});
