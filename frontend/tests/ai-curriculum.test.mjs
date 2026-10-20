import assert from "node:assert/strict";
import test from "node:test";
import { aiCurriculum, aiQualification } from "../lib/ai-software-developer.ts";

test("qualification structure accounts for every compulsory module and credit", () => {
  assert.deepEqual(aiCurriculum.map(group => group.modules.length), [12, 11, 3]);
  assert.deepEqual(aiCurriculum.map(group => group.modules.reduce((sum, item) => sum + item.credits, 0)), [86, 63, 60]);
  assert.equal(aiCurriculum.reduce((sum, group) => sum + group.credits, 0), aiQualification.credits);
  for (const group of aiCurriculum) {
    assert.equal(group.modules.reduce((sum, item) => sum + item.credits, 0), group.credits);
  }
});

test("module codes are unique, complete and retain their individual NQF levels", () => {
  const modules = aiCurriculum.flatMap(group => group.modules);
  assert.equal(new Set(modules.map(item => item.code)).size, 26);
  for (const [index, group] of aiCurriculum.entries()) {
    const prefix = ["KM", "PM", "WM"][index];
    assert.deepEqual(group.modules.map(item => item.code), group.modules.map((_, i) => `251201-002-00-${prefix}-${String(i + 1).padStart(2, "0")}`));
  }
  assert.deepEqual(aiCurriculum[0].modules.filter(item => item.level === 5).map(item => item.code.slice(-5)), ["KM-07", "KM-08", "KM-09"]);
  assert.deepEqual(aiCurriculum[1].modules.filter(item => item.level === 5).map(item => item.code.slice(-5)), ["PM-04", "PM-05", "PM-06", "PM-07", "PM-08", "PM-09"]);
  assert.ok(aiCurriculum[2].modules.every(item => item.level === 5));
});
