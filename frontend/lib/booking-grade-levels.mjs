/**
 * Student-facing grade/level choices are independent of tutor availability.
 * Tutor-specific labels can be added without hiding the standard curriculum choices.
 */
export const programmes = [
  ["caps", "CAPS"],
  ["ieb", "IEB"],
  ["tvet", "TVET"],
  ["university", "University"],
];

export const subjects = [
  ["mathematics", "Mathematics"],
  ["mathematical_literacy", "Mathematical Literacy"],
];

/** @type {Record<string, readonly string[]>} */
export const gradeLevelsByProgramme = {
  caps: ["Grade 10", "Grade 11", "Grade 12"],
  ieb: ["Grade 10", "Grade 11", "Grade 12"],
  tvet: [
    "N2",
    "N3",
    "N4",
    "N5",
    "N6",
    "NC(V) Level 2",
    "NC(V) Level 3",
    "NC(V) Level 4",
  ],
  university: ["Year 1", "Year 2", "Year 3", "Year 4", "Honours"],
};

/**
 * @param {string} programme
 * @param {string[]} [offeredLevels]
 * @returns {string[]}
 */
export function getGradeLevels(programme, offeredLevels = []) {
  const standard = gradeLevelsByProgramme[programme];
  if (!standard) return [];
  const additional = offeredLevels
    .filter((item) => typeof item === "string" && item.trim())
    .map((item) => item.trim())
    .sort((a, b) => a.localeCompare(b, "en-ZA", { numeric: true }));
  return [...new Set([...standard, ...additional])];
}
