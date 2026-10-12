import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import {
  getGradeLevels,
  programmes,
  gradeLevelsByProgramme,
} from "../lib/booking-grade-levels.mjs";

const page = fs.readFileSync(
  new URL("../app/book-online-live-class/page.tsx", import.meta.url),
  "utf8",
);
const filters = fs.readFileSync(
  new URL("../app/book-online-live-class/live-class-booking-filters.tsx", import.meta.url),
  "utf8",
);

test("all four programmes expose selectable grade/level choices without tutor availability", () => {
  assert.deepEqual(programmes.map(([id]) => id), ["caps", "ieb", "tvet", "university"]);
  for (const [programme] of programmes) {
    assert.ok(getGradeLevels(programme).length > 0, programme);
  }
  assert.deepEqual(getGradeLevels("caps"), ["Grade 10", "Grade 11", "Grade 12"]);
  assert.deepEqual(getGradeLevels("ieb"), ["Grade 10", "Grade 11", "Grade 12"]);
  assert.ok(getGradeLevels("tvet").includes("N3"));
  assert.ok(getGradeLevels("tvet").includes("NC(V) Level 4"));
  assert.ok(getGradeLevels("university").includes("Year 1"));
});

test("custom tutor grade labels supplement standard grades without duplicates", () => {
  assert.deepEqual(
    getGradeLevels("caps", ["Grade 12", "Grade 9", "Grade 9"]),
    ["Grade 10", "Grade 11", "Grade 12", "Grade 9"],
  );
  assert.deepEqual(getGradeLevels("unrecognized", ["Grade 12"]), []);
  assert.equal(gradeLevelsByProgramme.caps.includes("N3"), false);
});

test("booking form updates level choices and clears stale selections", () => {
  assert.ok(filters.includes("setProgramme(event.target.value);"));
  assert.ok(filters.includes("setSubject(event.target.value);"));
  assert.ok(filters.includes('setLevel("");'));
  assert.ok(filters.includes("getGradeLevels(programme, matchingOfferedLevels)"));
  assert.ok(filters.includes("<optgroup"));
  assert.ok(!filters.includes("disabled="), "grade selection must remain enabled");
});

test("server does not trust stale or cross-programme grade/level query strings", () => {
  assert.match(page, /const chosenLevel = levels\.includes\(level\) \? level : "";/);
  assert.match(page, /slot\.level === chosenLevel/);
  assert.match(page, /initialLevel=\{chosenLevel\}/);
});
