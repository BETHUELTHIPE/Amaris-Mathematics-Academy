import assert from "node:assert/strict";
import test from "node:test";
import { CUSTOM_CHOICE, getCurriculumTopics, resolveCurriculumFields, SCHOOL_GRADES } from "../lib/school-curriculum.mjs";
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
  new URL("../components/site/curriculum-fields.tsx", import.meta.url),
  "utf8",
);

test("all four programmes expose selectable grade/level choices without tutor availability", () => {
  assert.deepEqual(programmes.map(([id]) => id), ["caps", "ieb", "tvet", "university"]);
  for (const [programme] of programmes) {
    assert.ok(getGradeLevels(programme).length > 0, programme);
  }
  assert.deepEqual(getGradeLevels("caps"), SCHOOL_GRADES);
  assert.deepEqual(getGradeLevels("ieb"), SCHOOL_GRADES);
  assert.ok(getGradeLevels("tvet").includes("N3"));
  assert.ok(getGradeLevels("tvet").includes("NC(V) Level 4"));
  assert.ok(getGradeLevels("university").includes("Year 1"));
});

test("custom tutor grade labels supplement standard grades without duplicates", () => {
  assert.deepEqual(
    getGradeLevels("caps", ["Grade 12", "Grade 9", "Grade 9"]),
    SCHOOL_GRADES,
  );
  assert.deepEqual(getGradeLevels("unrecognized", ["Grade 12"]), []);
  assert.equal(gradeLevelsByProgramme.caps.includes("N3"), false);
});

test("booking form updates level choices and clears stale selections", () => {
  assert.ok(filters.includes("setProgramme(event.target.value);"));
  assert.ok(filters.includes("setSubject(event.target.value);"));
  assert.ok(filters.includes('setLevel("");'));
  assert.ok(filters.includes("getGradeLevels(programme,"));
  assert.ok(filters.includes("<optgroup"));
  assert.ok(!filters.includes("disabled="), "grade selection must remain enabled");
});

test("server does not trust stale or cross-programme grade/level query strings", () => {
  assert.match(page, /const chosenLevel = levels\.includes\(level\)/);
  assert.match(page, /slot\.level === chosenLevel/);
  assert.match(page, /initialLevel=\{chosenLevel\}/);
});


test("each school grade has chapter coverage with appropriate progression", () => {
  for (const programme of ["caps", "ieb"]) for (const level of SCHOOL_GRADES) {
    const chapters = getCurriculumTopics(programme, "mathematics", level).flatMap(group => group.chapters);
    assert.ok(chapters.length >= 10, programme + level);
    assert.equal(new Set(chapters).size, chapters.length);
    assert.ok(chapters.every(chapter => chapter.length >= 2 && chapter.length <= 180));
    const data = new FormData();
    const expected = {programme, subject: "mathematics", level, topic: chapters[0]};
    for (const [key, value] of Object.entries(expected)) data.set(key, value);
    assert.deepEqual(resolveCurriculumFields(data), expected);
  }
  const topics = level => getCurriculumTopics("caps", "mathematics", level).flatMap(group => group.chapters).join(" ");
  assert.match(topics("Grade 7"), /fractions/);
  assert.doesNotMatch(topics("Grade 7"), /Differentiation|Optimisation/);
  assert.match(topics("Grade 8"), /Pythagoras/);
  assert.match(topics("Grade 9"), /factorisation/);
  assert.match(topics("Grade 10"), /Trigonometric graphs/);
  assert.match(topics("Grade 11"), /Circle geometry/);
  assert.match(topics("Grade 12"), /Differentiation rules/);
});

test("Mathematical Literacy has only Grades 10–12, including with incompatible offered slots", () => {
  for (const programme of ["caps", "ieb"]) {
    assert.deepEqual(getGradeLevels(programme, ["Grade 7", "Grade 8", "Grade 9"], "mathematical_literacy"), SCHOOL_GRADES.slice(3));
    for (const grade of SCHOOL_GRADES.slice(0, 3)) assert.deepEqual(getCurriculumTopics(programme, "mathematical_literacy", grade), []);
    for (const grade of SCHOOL_GRADES.slice(3)) assert.ok(getCurriculumTopics(programme, "mathematical_literacy", grade).length > 0);
  }
});

test("custom chapters and academic modules preserve backend values and reject missing names", () => {
  const data = new FormData();
  for (const [key, value] of Object.entries({programme: "university", subject: "mathematics", level: CUSTOM_CHOICE, customLevel: " UNISA MAT2611 ", topic: CUSTOM_CHOICE, customTopic: " Assignment 2, Question 4 "})) data.set(key, value);
  assert.deepEqual(resolveCurriculumFields(data), {programme: "university", subject: "mathematics", level: "UNISA MAT2611", topic: "Assignment 2, Question 4"});
  data.set("programme", "ieb"); data.set("level", "Grade 7");
  assert.equal(resolveCurriculumFields(data).topic, "Assignment 2, Question 4");
  data.set("customTopic", " ");
  assert.throws(() => resolveCurriculumFields(data), /Choose a topic/);
  assert.equal(resolveCurriculumFields(data, false).level, "Grade 7");
  data.set("subject", "mathematical_literacy");
  assert.throws(() => resolveCurriculumFields(data, false), /Grades 7–9/);
});
