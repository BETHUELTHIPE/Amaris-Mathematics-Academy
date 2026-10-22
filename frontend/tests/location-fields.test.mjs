import assert from "node:assert/strict";
import test, { after } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
const vite = await createServer({ root: fileURLToPath(new URL("..", import.meta.url)), configFile: false, appType: "custom", server: { middlewareMode: true, hmr: false, ws: false } });
const { parseLocation, initialLocation, loadCountry } = await vite.ssrLoadModule("/lib/location-server.ts");
const { africanCountries, OTHER_LOCATION } = await vite.ssrLoadModule("/lib/location-data.ts");
after(() => vite.close());
const pretoria = { country: "ZA", province: "Gauteng", city: "Pretoria" };

test("all African country choices have matching offline province and city data", async () => {
  assert.equal(africanCountries.length, 58);
  assert.ok(africanCountries.some(country => country.code === "ZA"));
  assert.ok(africanCountries.some(country => country.code === "KE"));
  assert.ok(!africanCountries.some(country => country.code === "US"));
  for (const country of africanCountries) {
    const data = await loadCountry(country.code);
    assert.deepEqual(data, JSON.parse(await readFile(new URL("../public/data/locations/" + country.code + ".json", import.meta.url), "utf8")));
    assert.equal(data.name, country.name);
    assert.deepEqual(Object.keys(data.provinces), country.provinces);
  }
  assert.equal(Object.keys((await loadCountry("ZA")).provinces).length, 9);
  assert.deepEqual((await parseLocation(pretoria)).value, pretoria);
});
test("separate field errors reject omissions, whitespace, unknown countries and mismatched cities", async () => {
  for (const field of ["country", "province", "city"]) {
    for (const value of [undefined, "", "   "]) {
      const result = await parseLocation({ ...pretoria, [field]: value });
      assert.equal(result.value, null);
      assert.ok(result.errors[field], field);
    }
  }
  for (const country of ["US", "constructor", "__proto__", "../../ZA"]) {
    assert.ok((await parseLocation({ ...pretoria, country })).errors.country);
  }
  for (const province of ["constructor", "__proto__", "toString"]) assert.ok((await parseLocation({ ...pretoria, province })).errors.province);
  assert.ok((await parseLocation({ ...pretoria, province: "Western Cape" })).errors.city);
  assert.ok((await parseLocation({ ...pretoria, country: "KE" })).errors.province);
  assert.ok((await parseLocation({ ...pretoria, city: "Not a listed city" })).errors.city);
});
test("an explicitly unlisted place is accepted only with its separate required name", async () => {
  const other = { country: "ZA", province: OTHER_LOCATION, provinceOther: " Synthetic Region ", city: OTHER_LOCATION, cityOther: " Synthetic Town " };
  assert.deepEqual((await parseLocation(other)).value, { country: "ZA", province: "Synthetic Region", city: "Synthetic Town" });
  assert.ok((await parseLocation({ ...other, provinceOther: "" })).errors.provinceOther);
  assert.ok((await parseLocation({ ...other, cityOther: "" })).errors.cityOther);
  assert.ok((await parseLocation({ ...other, cityOther: "x".repeat(161) })).errors.cityOther);
});
test("server-rendered selections preserve valid choices and support the no-JavaScript Other flow", async () => {
  const initial = await initialLocation(pretoria);
  assert.equal(initial.city, "Pretoria");
  const other = await initialLocation({ country: "ZA", province: OTHER_LOCATION, city: OTHER_LOCATION });
  assert.equal(other.province, OTHER_LOCATION);
  assert.equal(other.city, OTHER_LOCATION);
  assert.equal((await initialLocation({ country: "KE", province: "Gauteng", city: "Pretoria" })).province, "");
});

