import type { Course } from "@/lib/courses";

export type CourseFilter = "All" | "CAPS" | "TVET" | "University";

function normalize(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export function courseMatchesSearch(
  course: Course,
  query: string,
  filter: CourseFilter,
): boolean {
  const tokens = normalize(query).split(/\s+/).filter(Boolean);
  const haystack = normalize(
    [
      course.title,
      course.description,
      course.curriculum,
      course.level,
      ...course.modules,
      ...course.outcomes,
    ].join(" "),
  );
  const matchesText = tokens.every((token) => haystack.includes(token));

  const curriculum = normalize(course.curriculum);
  const level = normalize(course.level);
  const matchesFilter =
    filter === "All" ||
    (filter === "TVET"
      ? level.includes("tvet") || curriculum.includes("nated")
      : filter === "University"
        ? level.includes("university") || curriculum.includes("higher education")
        : curriculum.includes(normalize(filter)));

  return matchesText && matchesFilter;
}
